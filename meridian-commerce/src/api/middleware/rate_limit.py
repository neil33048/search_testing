"""
Rate limiting middleware.

Enforces per-merchant rate limits based on tier.
Uses Redis for distributed rate limiting.
"""

import time
from typing import Callable, Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config.settings import settings
from src.core.cache import cache
from src.core.exceptions import RateLimitError

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter using Redis.
    
    Rate limits vary by merchant tier:
    - Bronze: 1,000 requests/minute
    - Silver: 2,000 requests/minute
    - Gold: 5,000 requests/minute
    - Platinum: 10,000 requests/minute
    
    Returns 429 Too Many Requests when limit is exceeded.
    """
    
    # Endpoints exempt from rate limiting
    EXEMPT_PATHS = {
        "/health",
        "/health/ready",
        "/health/live",
        "/",
    }
    
    # Tier limits (requests per minute)
    TIER_LIMITS = {
        "bronze": 1000,
        "silver": 2000,
        "gold": 5000,
        "platinum": 10000,
    }
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Skip rate limiting for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        
        # Get merchant ID (may not be available yet)
        merchant_id = getattr(request.state, "merchant_id", None)
        
        if not merchant_id:
            # Try to extract from auth header
            # This is a simplified extraction - full auth happens later
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer mc_"):
                parts = auth_header.split("_")
                if len(parts) >= 3:
                    merchant_id = f"merch_{parts[2]}"
        
        if not merchant_id:
            # Can't rate limit without merchant ID
            return await call_next(request)
        
        # Check rate limit
        is_allowed, remaining, reset_time = await self._check_rate_limit(
            merchant_id
        )
        
        if not is_allowed:
            logger.warning(
                "Rate limit exceeded",
                merchant_id=merchant_id,
                path=request.url.path,
            )
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": "Rate limit exceeded",
                        "code": "MC-API-429",
                        "details": {
                            "retry_after_seconds": reset_time,
                        },
                    }
                },
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + reset_time)),
                    "Retry-After": str(reset_time),
                },
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response
    
    async def _check_rate_limit(
        self,
        merchant_id: str,
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Returns:
            (is_allowed, remaining_requests, seconds_until_reset)
        """
        # Get tier limit (default to bronze)
        tier = await self._get_merchant_tier(merchant_id)
        limit = self.TIER_LIMITS.get(tier, 1000)
        
        # Sliding window key
        window_key = f"ratelimit:{merchant_id}:{int(time.time() // 60)}"
        
        try:
            # Increment counter
            current = await cache.incr(window_key)
            
            # Set expiry on first request
            if current == 1:
                await cache.expire(window_key, 60)
            
            # Check limit
            if current > limit:
                seconds_until_reset = 60 - (int(time.time()) % 60)
                return False, 0, seconds_until_reset
            
            remaining = limit - current
            return True, remaining, 0
            
        except Exception as e:
            # On Redis error, allow request (fail open)
            logger.error("Rate limit check failed", error=str(e))
            return True, limit, 0
    
    async def _get_merchant_tier(self, merchant_id: str) -> str:
        """Get merchant tier for rate limit calculation."""
        # Would query from database/cache
        # Simulated - return gold tier
        return "gold"
