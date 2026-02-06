"""
Meridian Commerce Platform - API Entry Point

FastAPI application serving the Meridian Commerce REST API.
Handles merchant dashboard, analytics, recommendations, and events.

API versioning: /api/v1/...
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from src.api.middleware.logging import LoggingMiddleware
from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.routes import analytics, events, merchants, recommendations, health
from src.core.cache import cache
from src.core.database import close_database, init_database
from src.core.exceptions import MeridianError

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown of services.
    """
    # Startup
    logger.info("Starting Meridian Commerce API", version=settings.api_version)
    
    # Initialize database
    await init_database()
    
    # Connect to cache
    await cache.connect()
    
    logger.info("API startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API")
    
    await close_database()
    await cache.disconnect()
    
    logger.info("API shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description="""
    Meridian Commerce Platform API
    
    Enterprise e-commerce analytics platform powering real-time insights,
    personalized recommendations, and event tracking.
    
    ## Key Components
    
    - **Beacon**: Event collection and tracking
    - **Pulse**: Real-time analytics and dashboards
    - **Catalyst**: ML-powered recommendations
    - **Forge**: Data pipeline management
    
    ## Authentication
    
    API requests require a Bearer token in the Authorization header:
    ```
    Authorization: Bearer <api_key>
    ```
    
    ## Rate Limits
    
    Rate limits vary by merchant tier:
    - Bronze: 1,000 requests/minute
    - Silver: 2,000 requests/minute
    - Gold: 5,000 requests/minute
    - Platinum: 10,000 requests/minute
    """,
    version=settings.api_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)


# =============================================================================
# Middleware
# =============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
app.add_middleware(LoggingMiddleware)

# Rate limiting
if settings.is_production:
    app.add_middleware(RateLimitMiddleware)


# =============================================================================
# Exception Handlers
# =============================================================================

@app.exception_handler(MeridianError)
async def meridian_error_handler(
    request: Request,
    exc: MeridianError,
) -> JSONResponse:
    """Handle all Meridian-specific exceptions."""
    logger.warning(
        "Request error",
        error_code=exc.code,
        message=exc.message,
        path=request.url.path,
    )
    
    # Map error codes to HTTP status codes
    status_code_map = {
        "MC-API-400": 400,
        "MC-API-401": 401,
        "MC-API-403": 403,
        "MC-API-404": 404,
        "MC-API-409": 409,
        "MC-API-429": 429,
    }
    
    status_code = 500
    for prefix, code in status_code_map.items():
        if exc.code.startswith(prefix):
            status_code = code
            break
    
    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(
        "Unexpected error",
        error=str(exc),
        path=request.url.path,
        exc_info=True,
    )
    
    # Don't expose internal errors in production
    if settings.is_production:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "An internal error occurred",
                    "code": "MC-ERR-500",
                }
            },
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": str(exc),
                    "code": "MC-ERR-500",
                }
            },
        )


# =============================================================================
# Routes
# =============================================================================

# Health check
app.include_router(health.router, tags=["Health"])

# API v1 routes
api_v1_prefix = f"/api/{settings.api_version}"

app.include_router(
    events.router,
    prefix=f"{api_v1_prefix}/events",
    tags=["Events (Beacon)"],
)

app.include_router(
    analytics.router,
    prefix=f"{api_v1_prefix}/analytics",
    tags=["Analytics (Pulse)"],
)

app.include_router(
    recommendations.router,
    prefix=f"{api_v1_prefix}/recommendations",
    tags=["Recommendations (Catalyst)"],
)

app.include_router(
    merchants.router,
    prefix=f"{api_v1_prefix}/merchants",
    tags=["Merchants"],
)


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/")
async def root() -> dict[str, Any]:
    """API root - returns service info."""
    return {
        "service": "Meridian Commerce API",
        "version": settings.api_version,
        "status": "healthy",
        "docs": "/docs" if settings.debug else None,
    }
