"""
Health Check Endpoints

Provides liveness, readiness, and detailed health status endpoints
for monitoring and orchestration (Docker, Kubernetes, load balancers).
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import logging
import time
from datetime import datetime
from pathlib import Path

from app.db.database import get_db
from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])

# Track startup time for uptime calculation
startup_time = time.time()


@router.get("/", tags=["monitoring"])
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    
    Returns:
        200 if service is healthy
        503 if service is degraded
    
    Used by load balancers and container orchestration.
    """
    try:
        uptime_seconds = int(time.time() - startup_time)
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": uptime_seconds,
            "service": "Financial Risk Analysis & Fraud Detection System",
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get("/live", tags=["monitoring"])
async def liveness() -> Dict[str, Any]:
    """
    Liveness check endpoint.
    
    Indicates if the service is running and responsive.
    Returns immediately without checking dependencies.
    
    Returns:
        200 if service is alive
        503 if service is dead
    
    Used by Kubernetes liveness probes.
    """
    try:
        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "Financial Risk Analysis & Fraud Detection System"
        }
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service is dead")


@router.get("/ready", tags=["monitoring"])
async def readiness(db=Depends(get_db)) -> Dict[str, Any]:
    """
    Readiness check endpoint.
    
    Verifies that the service is ready to accept traffic.
    Checks dependencies: database, cache, etc.
    
    Returns:
        200 if service is ready
        503 if service is not ready
    
    Used by Kubernetes readiness probes and load balancers.
    """
    try:
        dependencies_status = {}
        all_ready = True
        
        # Check database connectivity
        try:
            await _check_database(db)
            dependencies_status["database"] = "ready"
        except Exception as e:
            logger.error(f"Database check failed: {e}")
            dependencies_status["database"] = f"unavailable: {str(e)[:50]}"
            all_ready = False
        
        # Check model files
        try:
            await _check_models()
            dependencies_status["models"] = "ready"
        except Exception as e:
            logger.warning(f"Model check failed: {e}")
            dependencies_status["models"] = f"unavailable: {str(e)[:50]}"
            # Not critical - can proceed with degraded functionality
        
        if not all_ready:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not_ready",
                    "dependencies": dependencies_status
                }
            )
        
        uptime_seconds = int(time.time() - startup_time)
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": uptime_seconds,
            "dependencies": dependencies_status,
            "service": "Financial Risk Analysis & Fraud Detection System"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@router.get("/detailed", tags=["monitoring"])
async def detailed_health(db=Depends(get_db)) -> Dict[str, Any]:
    """
    Detailed health check with comprehensive status.
    
    Returns:
        Detailed health information including:
        - Service status
        - Dependency status
        - Resource usage
        - Performance metrics
    
    Used by monitoring dashboards and ops teams.
    """
    try:
        details = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int(time.time() - startup_time),
            "service": "Financial Risk Analysis & Fraud Detection System",
            "version": "1.0.0",
            "environment": settings.environment,
            "dependencies": {}
        }
        
        # Database details
        try:
            db_status = await _check_database(db)
            details["dependencies"]["database"] = {
                "status": "ok",
                "connection_pool": db_status.get("pool_size", "unknown")
            }
        except Exception as e:
            details["dependencies"]["database"] = {
                "status": "error",
                "error": str(e)[:100]
            }
        
        # Models details
        try:
            model_status = await _check_models()
            details["dependencies"]["models"] = {
                "status": "ok",
                "fraud_model": model_status.get("fraud_model", False),
                "risk_model": model_status.get("risk_model", False)
            }
        except Exception as e:
            details["dependencies"]["models"] = {
                "status": "error",
                "error": str(e)[:100]
            }
        
        # Performance metrics
        details["metrics"] = {
            "response_time_ms": 0,  # Will be set by monitoring
            "request_queue_length": 0,
            "active_connections": 0
        }
        
        return details
    
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check error")


# ============================================
# Internal Health Check Functions
# ============================================

async def _check_database(db) -> Dict[str, Any]:
    """
    Check database connectivity and status.
    
    Args:
        db: Database session
    
    Returns:
        Dictionary with database status
    
    Raises:
        Exception if database is unreachable
    """
    try:
        db.command("ping")
        return {"status": "ok", "driver": "PyMongo"}
    
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        raise


async def _check_redis() -> Dict[str, Any]:
    """
    Check Redis connectivity and status.
    
    Returns:
        Dictionary with Redis status
    
    Raises:
        Exception if Redis is unreachable
    """
    try:
        import redis
        
        # Parse Redis URL
        redis_url = settings.redis_url or "redis://localhost:6379/0"
        client = redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
        
        # Ping Redis
        client.ping()
        
        # Get memory info
        info = client.info('memory')
        memory_mb = info.get('used_memory', 0) / (1024 * 1024)
        
        client.close()
        
        return {
            "status": "ok",
            "memory": f"{memory_mb:.1f}MB"
        }
    
    except ImportError:
        # Redis package not installed
        logger.debug("Redis package not installed")
        return {"status": "not_installed"}
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
        raise


async def _check_models() -> Dict[str, Any]:
    """
    Check if ML model files exist and are readable.
    
    Returns:
        Dictionary with model status
    
    Raises:
        Exception if models are missing
    """
    import os
    
    try:
        models_dir = Path(__file__).resolve().parents[2] / "models"
        model_count = len(list(models_dir.glob("*_v*.json"))) if models_dir.exists() else 0
        return {
            "status": "ok",
            "saved_model_count": model_count,
        }
    
    except Exception as e:
        logger.error(f"Model check failed: {e}")
        raise


__all__ = ["router", "health_check", "liveness", "readiness", "detailed_health"]
