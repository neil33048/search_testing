"""
Authentication middleware.

Handles API key validation and merchant context extraction.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.exceptions import AuthenticationError, AuthorizationError

security = HTTPBearer()


async def get_current_merchant(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Extract and validate merchant from API key.
    
    API keys follow the format: mc_{env}_{merchant_id}_{random}
    - mc_live_merch123_xxxxxxxxxxxx (production)
    - mc_test_merch123_xxxxxxxxxxxx (test/sandbox)
    
    Returns the merchant_id from the validated key.
    """
    token = credentials.credentials
    
    # In production, would validate against secrets manager/database
    # and extract merchant_id from the key
    
    # Simple validation for demo
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )
    
    # Extract merchant ID from key format
    # Format: mc_{env}_{merchant_id}_{random}
    parts = token.split("_")
    
    if len(parts) >= 3 and parts[0] == "mc":
        merchant_id = f"merch_{parts[2]}"
        
        # Store in request state for logging
        request.state.merchant_id = merchant_id
        request.state.api_key_prefix = "_".join(parts[:3])
        
        return merchant_id
    
    # Fallback for demo - accept any token
    return "merch_demo123"


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> bool:
    """
    Require admin privileges.
    
    Admin keys have a special format: mc_admin_{user_id}_{random}
    """
    token = credentials.credentials
    
    if not token.startswith("mc_admin_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    return True


async def get_optional_user(
    request: Request,
) -> Optional[str]:
    """
    Get user ID from request if available.
    
    User context can come from:
    - JWT token (for logged-in users)
    - X-User-ID header (for server-side calls)
    """
    # Check header first
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return user_id
    
    # Check JWT if present
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # Would decode JWT and extract user_id
        pass
    
    return None


class APIKeyValidator:
    """
    Validates API keys and manages rate limiting.
    
    Key types:
    - Live keys (mc_live_*): Production use, full rate limits
    - Test keys (mc_test_*): Sandbox mode, relaxed validation
    - Admin keys (mc_admin_*): Internal use only
    """
    
    def __init__(self):
        self._key_cache: dict[str, dict] = {}
    
    async def validate_key(self, api_key: str) -> dict:
        """
        Validate an API key and return metadata.
        
        Returns:
            {
                "valid": True,
                "merchant_id": "merch_xxx",
                "environment": "live",
                "tier": "gold",
                "rate_limit": 5000,
            }
        """
        # Check cache first
        if api_key in self._key_cache:
            return self._key_cache[api_key]
        
        # Would query database/secrets manager
        # Simulated response
        result = {
            "valid": True,
            "merchant_id": "merch_demo123",
            "environment": "live",
            "tier": "gold",
            "rate_limit": 5000,
        }
        
        # Cache result
        self._key_cache[api_key] = result
        
        return result
    
    def get_rate_limit(self, tier: str) -> int:
        """Get rate limit for merchant tier."""
        limits = {
            "bronze": 1000,
            "silver": 2000,
            "gold": 5000,
            "platinum": 10000,
        }
        return limits.get(tier, 1000)
