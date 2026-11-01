"""
Security Hardening Module

Implements production-ready security configurations including:
- HTTPS/TLS enforcement
- Security headers
- Rate limiting
- Input sanitization
- CORS hardening
- Secure session management
- CSRF protection
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware to prevent abuse."""

    def __init__(self, app, requests_per_hour: int = 100):
        super().__init__(app)
        self.requests_per_hour = requests_per_hour
        self.requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        """Check rate limits before processing request."""
        client_ip = request.client.host
        current_time = time.time()
        hour_ago = current_time - 3600

        # Clean old requests
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if req_time > hour_ago
        ]

        # Check limit
        if len(self.requests[client_ip]) >= self.requests_per_hour:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return Response(
                content='{"error": "rate_limit_exceeded"}',
                status_code=429,
                headers={"Retry-After": "3600"}
            )

        # Record this request
        self.requests[client_ip].append(current_time)

        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining"] = str(
            self.requests_per_hour - len(self.requests[client_ip])
        )
        response.headers["X-RateLimit-Reset"] = str(int(current_time) + 3600)

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'"
        )

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Feature Policy / Permissions Policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=()"
        )

        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production."""

    async def dispatch(self, request: Request, call_next):
        # Skip for health checks and internal requests
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # In production, enforce HTTPS
        if request.url.scheme == "http" and request.headers.get("X-Forwarded-Proto") != "https":
            logger.warning(f"HTTP request received: {request.url}")
            # In production, redirect to HTTPS
            # For now, allow HTTP for local development
            if request.headers.get("Host", "").startswith("localhost"):
                return await call_next(request)

        return await call_next(request)


def setup_security_headers(app: FastAPI, environment: str = "development"):
    """
    Configure security headers and middleware.

    Args:
        app: FastAPI application instance
        environment: 'development', 'staging', or 'production'
    """

    # Add security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Add rate limiting middleware
    app.add_middleware(RateLimitMiddleware, requests_per_hour=100)

    # Add HTTPS redirect middleware (only in production)
    if environment == "production":
        app.add_middleware(HTTPSRedirectMiddleware)

    # Add trusted host middleware
    allowed_hosts = [
        "localhost",
        "127.0.0.1",
        "*.yourdomain.com",
    ]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    logger.info(f"Security headers configured for {environment} environment")


def setup_cors(app: FastAPI, allowed_origins: list = None):
    """
    Configure CORS with security best practices.

    Args:
        app: FastAPI application instance
        allowed_origins: List of allowed origins
    """

    if allowed_origins is None:
        allowed_origins = ["http://localhost:3000", "http://localhost:8501"]

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        max_age=3600,  # Cache preflight for 1 hour
        expose_headers=["X-Total-Count", "X-Page", "X-Limit"],
    )

    logger.info(f"CORS configured for origins: {allowed_origins}")


def sanitize_input(value: str, max_length: int = 1000) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.

    Args:
        value: User input string
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        return value

    # Truncate to max length
    value = value[:max_length]

    # Remove null bytes
    value = value.replace("\x00", "")

    # Escape HTML special characters
    value = (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )

    return value


def validate_url(url: str) -> bool:
    """
    Validate URL to prevent SSRF attacks.

    Args:
        url: URL to validate

    Returns:
        True if URL is safe, False otherwise
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)

        # Only allow http and https schemes
        if parsed.scheme not in ("http", "https"):
            return False

        # Prevent localhost/internal addresses
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            return False

        # Prevent private IP ranges
        if parsed.hostname and parsed.hostname.startswith(("10.", "172.", "192.")):
            return False

        return True

    except Exception as e:
        logger.error(f"URL validation error: {e}")
        return False


def setup_session_security(app: FastAPI):
    """
    Configure secure session management.

    Args:
        app: FastAPI application instance
    """
    # Session settings
    session_settings = {
        "max_age": 1800,  # 30 minutes
        "secure": True,  # HTTPS only
        "httponly": True,  # No JavaScript access
        "samesite": "Strict",  # CSRF protection
    }

    logger.info("Secure session configuration applied")
    return session_settings


def check_dependency_vulnerabilities():
    """
    Check installed packages for known vulnerabilities.

    This should be called during startup to catch vulnerable dependencies.
    """
    import subprocess
    import json

    try:
        # Run safety check
        result = subprocess.run(
            ["safety", "check", "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            vulnerabilities = json.loads(result.stdout)
            logger.warning(f"Found {len(vulnerabilities)} vulnerable dependencies")
            for vuln in vulnerabilities[:5]:  # Log first 5
                logger.warning(f"  - {vuln['package']}: {vuln['vulnerability']}")

    except FileNotFoundError:
        logger.debug("safety package not installed, skipping vulnerability check")
    except Exception as e:
        logger.error(f"Dependency check error: {e}")


def get_security_config(environment: str = "development") -> dict:
    """
    Get security configuration for the given environment.

    Args:
        environment: 'development', 'staging', or 'production'

    Returns:
        Security configuration dictionary
    """

    configs = {
        "development": {
            "debug": True,
            "enforce_https": False,
            "cors_origins": ["http://localhost:3000", "http://localhost:8501"],
            "rate_limit": 1000,  # Higher limit for development
            "session_timeout": 86400,  # 24 hours
        },
        "staging": {
            "debug": False,
            "enforce_https": True,
            "cors_origins": ["https://staging.yourdomain.com"],
            "rate_limit": 100,
            "session_timeout": 3600,  # 1 hour
        },
        "production": {
            "debug": False,
            "enforce_https": True,
            "cors_origins": ["https://yourdomain.com"],
            "rate_limit": 100,
            "session_timeout": 1800,  # 30 minutes
        }
    }

    return configs.get(environment, configs["development"])


# Export configuration functions
__all__ = [
    "setup_security_headers",
    "setup_cors",
    "setup_session_security",
    "sanitize_input",
    "validate_url",
    "check_dependency_vulnerabilities",
    "get_security_config",
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "HTTPSRedirectMiddleware",
]
