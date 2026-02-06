"""
Health check endpoints.

Used by load balancers and container orchestrators
to determine service health and readiness.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.core.cache import cache
from src.core.database import check_database_connection

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Basic health check.
    
    Returns 200 if the service is running.
    Used for liveness probes.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check with dependency verification.
    
    Verifies connectivity to:
    - Database (PostgreSQL)
    - Cache (Redis)
    
    Returns 503 if any dependency is unhealthy.
    Used for readiness probes.
    """
    checks = {}
    is_ready = True
    
    # Check database
    try:
        db_healthy = await check_database_connection()
        checks["database"] = "healthy" if db_healthy else "unhealthy"
        if not db_healthy:
            is_ready = False
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        is_ready = False
    
    # Check cache
    try:
        cache_healthy = await cache.health_check()
        checks["cache"] = "healthy" if cache_healthy else "unhealthy"
        if not cache_healthy:
            is_ready = False
    except Exception as e:
        checks["cache"] = f"error: {str(e)}"
        is_ready = False
    
    response = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response,
    )


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """
    Simple liveness check.
    
    Always returns 200 if the process is running.
    Used by Kubernetes liveness probes.
    """
    return {"status": "alive"}
