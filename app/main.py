"""
Main FastAPI application initialization and configuration.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.db.database import check_database, close_db, initialize_database
from app.api import auth, transactions, fraud_rules, fraud_assessment, alert_management, alert_dashboard, analytics, users, models, audit_logs, health
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Create FastAPI application
app = FastAPI(
    title="Financial Risk Analysis and Hybrid Fraud Detection System",
    description="Production-grade fraud detection and risk scoring system",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url="/api/redoc" if settings.is_development else None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ForwardedPrefixMiddleware:
    """Use the reverse-proxy prefix (e.g. /backend) as root_path so the
    Swagger UI and OpenAPI server URLs resolve correctly behind the proxy."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for name, value in scope.get("headers", []):
                if name == b"x-forwarded-prefix":
                    prefix = value.decode("latin-1").rstrip("/")
                    if prefix.startswith("/") and not scope["path"].startswith(prefix):
                        scope = dict(scope, root_path=prefix)
                    break
        await self.app(scope, receive, send)


app.add_middleware(ForwardedPrefixMiddleware)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "1.0.0"
    }

# Include routers
app.include_router(auth.router)
app.include_router(auth.router, prefix="/api")
app.include_router(transactions.router)
app.include_router(transactions.router, prefix="/api")
app.include_router(fraud_rules.router)
app.include_router(fraud_assessment.router)
app.include_router(alert_management.router)
app.include_router(alert_dashboard.router)
app.include_router(analytics.router)
app.include_router(users.router)
app.include_router(models.router)
app.include_router(audit_logs.router)
app.include_router(health.router)


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with consistent response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error" if not settings.is_development else str(exc),
            "status_code": 500,
        }
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database tables and log startup."""
    logger.info(f"Starting application in {settings.environment} mode")
    logger.info("Connecting to MongoDB database %s", settings.mongodb_database)

    try:
        if (
            settings.model_storage_backend.lower() == "atlas"
            and len(settings.model_artifact_signing_key.encode("utf-8")) < 32
        ):
            raise RuntimeError(
                "MODEL_ARTIFACT_SIGNING_KEY must be configured with at least 32 bytes."
            )
        check_database()
        initialize_database()
        logger.info("MongoDB indexes initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    logger.info("Shutting down application")
    close_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower()
    )
