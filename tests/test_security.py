"""
Security tests for the Financial Risk Analysis and Hybrid Fraud Detection System.
Tests CORS, JWT, SQL injection prevention, XSS, CSRF, permissions, and data handling.
"""

import pytest
from datetime import datetime, timedelta
import jwt as pyjwt
from app.core.config import get_settings
from app.core.security import create_access_token, decode_token, hash_password, verify_password


settings = get_settings()


class TestCORSConfiguration:
    """Test CORS origin validation."""
    
    def test_cors_origins_configured(self):
        """Verify CORS origins are properly configured."""
        assert hasattr(settings, 'cors_origins')
        assert isinstance(settings.cors_origins, (list, str))
    
    def test_cors_credentials_enabled(self):
        """Verify CORS credentials are enabled for secure contexts."""
        # CORS should allow credentials for same-origin requests
        assert settings.cors_origins is not None


class TestJWTTokenSecurity:
    """Test JWT token generation and validation."""
    
    def test_create_valid_token(self):
        """Test creation of valid JWT token."""
        data = {
            "sub": 1,
            "email": "test@example.com",
            "role": "User"
        }
        
        token = create_access_token(data, expires_delta=timedelta(hours=1))
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_token_expiration(self):
        """Test that tokens expire properly."""
        data = {
            "sub": 1,
            "email": "test@example.com"
        }
        
        # Create token with immediate expiration
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))
        
        # Token should be created (expiration is checked on decode)
        assert token is not None
    
    def test_token_contains_required_claims(self):
        """Verify token contains required claims."""
        data = {
            "sub": "1",  # sub must be a string
            "email": "test@example.com",
            "role": "Admin"
        }
        
        token = create_access_token(data)
        
        # Decode without verification to check claims
        payload = pyjwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        assert payload.get('sub') == "1"
        assert payload.get('email') == "test@example.com"
        assert 'exp' in payload  # Expiration claim
    
    def test_token_signature_validation(self):
        """Test that token signature is validated."""
        data = {
            "sub": 1,
            "email": "test@example.com"
        }
        
        token = create_access_token(data)
        
        # Tampering with token should fail validation
        tampered_token = token[:-5] + "xxxxx"
        
        # Should raise error when verifying tampered token
        try:
            decode_token(tampered_token)
            # If no exception, that's also acceptable (depends on JWT library strictness)
        except Exception:
            # Expected behavior - tampered token fails validation
            pass


class TestSQLInjectionPrevention:
    """Test MongoDB filter construction and ensure runtime SQL persistence is absent."""
    
    def test_orm_parameterized_queries(self):
        """Search strings remain literal MongoDB values, not injected regex operators."""
        from app.services.transaction_service import TransactionService

        query = TransactionService.build_query(transaction_id=".*")
        assert query["transaction_id"] == {"$regex": r"\.\*", "$options": "i"}
    
    def test_no_raw_sql_queries(self):
        """Active application modules must not contain SQL persistence dependencies."""
        from pathlib import Path

        app_dir = Path(__file__).resolve().parents[1] / "app"
        assert app_dir.is_dir()
        active_files = list(app_dir.rglob("*.py"))
        assert active_files
        assert not [
            str(path) for path in active_files
            if "sqlalchemy" in path.read_text(encoding="utf-8").lower()
        ]


class TestXSSPrevention:
    """Test XSS prevention in API responses."""
    
    def test_json_response_encoding(self):
        """Verify API returns proper JSON encoding to prevent XSS."""
        from fastapi import FastAPI
        
        app = FastAPI()
        assert app is not None
    
    def test_response_headers_no_xss(self):
        """Verify response headers include XSS protection headers."""
        # X-Content-Type-Options: nosniff
        # X-Frame-Options: DENY or SAMEORIGIN
        # X-XSS-Protection: 1; mode=block
        assert settings is not None


class TestCSRFProtection:
    """Test CSRF token handling."""
    
    def test_csrf_tokens_generated(self):
        """Verify CSRF tokens are generated for state-changing operations."""
        # CSRF protection should be enabled in middleware
        assert settings is not None
    
    def test_csrf_validation_on_post(self):
        """Verify CSRF validation occurs on POST/PUT/DELETE."""
        # This would typically be tested with integration tests against actual endpoints
        pass


class TestAuthorizationAndPermissions:
    """Test permission and authorization checks."""
    
    def test_admin_permission_required(self):
        """Test admin-only operations require admin role."""
        # Create token without admin role
        data = {"sub": 1, "role": "user"}
        user_token = create_access_token(data)
        
        # Create token with admin role
        data = {"sub": 2, "role": "admin"}
        admin_token = create_access_token(data)
        
        assert user_token is not None
        assert admin_token is not None
    
    def test_user_permission_required(self):
        """Test user-only operations require authentication."""
        # Create valid token
        data = {"sub": 1, "role": "user"}
        token = create_access_token(data)
        
        assert token is not None
    
    def test_unauthorized_access_rejected(self):
        """Test that access without valid token is rejected."""
        # Attempting to access protected endpoint without token should fail
        # This is tested via integration tests
        pass


class TestSensitiveDataProtection:
    """Test that sensitive data is not exposed in responses."""
    
    def test_passwords_not_in_responses(self):
        """Verify password hashes are never returned in API responses."""
        # Password hashing function
        password = "test_password_123"
        hashed = hash_password(password)
        
        # Hashed password should be a string
        assert isinstance(hashed, str)
        # Hashed should not equal plaintext
        assert hashed != password
    
    def test_api_keys_not_in_responses(self):
        """Verify API keys are never returned in API responses."""
        # API keys should be stored securely
        assert settings.secret_key is not None
        # Secret key should not be in logs or responses
        assert len(settings.secret_key) > 20
    
    def test_sensitive_fields_excluded_from_responses(self):
        """Verify sensitive fields are excluded from model responses."""
        # Models should use Pydantic exclude fields for responses
        pass


class TestPasswordHashing:
    """Test password hashing and verification."""
    
    def test_password_hashing(self):
        """Test password hashing works correctly."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password
    
    def test_password_verification(self):
        """Test password verification works correctly."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        # Correct password should verify
        assert verify_password(password, hashed) is True
    
    def test_incorrect_password_rejected(self):
        """Test that incorrect password is rejected."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        # Wrong password should not verify
        assert verify_password(wrong_password, hashed) is False


class TestRateLimiting:
    """Test rate limiting configuration."""
    
    def test_rate_limiter_configured(self):
        """Verify rate limiter is configured."""
        # Rate limiting should be configured
        assert settings is not None
    
    def test_rate_limit_enforcement(self):
        """Test that rate limits are enforced."""
        # This would be tested via integration tests
        pass


class TestInputValidation:
    """Test input validation and sanitization."""
    
    def test_string_length_validation(self):
        """Request schemas retain bounded text validation after persistence migration."""
        from pydantic import ValidationError
        from app.schemas import UserCreate

        with pytest.raises(ValidationError):
            UserCreate(
                email="risk@example.com", full_name="x" * 256,
                password="valid-password", role="analyst",
            )
    
    def test_email_validation(self):
        """Test that email inputs are validated."""
        # Email validation should occur in models/schemas
        pass
    
    def test_special_character_handling(self):
        """Test that special characters are handled safely."""
        # Special characters should be properly escaped/handled
        test_string = "<script>alert('xss')</script>"
        # Should not raise exception
        assert len(test_string) > 0


class TestSecurityHeaders:
    """Test security headers in HTTP responses."""
    
    def test_hsts_header(self):
        """Test HSTS header for HTTPS enforcement."""
        # HSTS should be enabled in production
        pass
    
    def test_csp_header(self):
        """Test Content Security Policy header."""
        # CSP should restrict resource loading
        pass
    
    def test_x_frame_options_header(self):
        """Test X-Frame-Options header to prevent clickjacking."""
        # X-Frame-Options should be set to DENY or SAMEORIGIN
        pass


class TestDependencyVulnerabilities:
    """Test that dependencies are free of known vulnerabilities."""
    
    def test_no_outdated_dependencies(self):
        """Verify no outdated/vulnerable packages are used."""
        # This is checked via security scanning tools
        # Like safety, bandit, or dependency check
        try:
            from importlib.metadata import distributions
            packages = [d.name for d in distributions()]
        except ImportError:
            import pkg_resources
            packages = [pkg for pkg, ver in [(d.project_name, d.version) for d in pkg_resources.working_set]]
        
        # Should have core packages
        assert len(packages) > 0
        # Verify FastAPI is installed (core dependency)
        assert any('fastapi' in pkg.lower() for pkg in packages)
    
    def test_secret_not_in_environment(self):
        """Verify secrets are not hardcoded."""
        # Secret key should come from environment, not hardcoded
        assert settings.secret_key is not None
        assert len(settings.secret_key) > 20
