"""
Merchants API endpoints.

Manage merchant accounts and settings.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.middleware.auth import get_current_merchant, require_admin

router = APIRouter()


class MerchantResponse(BaseModel):
    """Merchant data response."""
    
    id: str
    name: str
    tier: str
    status: str
    gmv_mtd: float
    gmv_12m: float
    total_customers: int
    total_orders: int


class MerchantSettingsUpdate(BaseModel):
    """Update merchant settings."""
    
    name: Optional[str] = None
    contact_email: Optional[str] = None
    webhook_url: Optional[str] = None
    
    # Beacon settings
    beacon_enabled: Optional[bool] = None
    beacon_domains: Optional[list[str]] = None
    
    # Catalyst settings
    catalyst_enabled: Optional[bool] = None
    
    # Notification settings
    slack_webhook_url: Optional[str] = None


@router.get("/me")
async def get_current_merchant_info(
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get current merchant information.
    
    Returns merchant profile, tier, and account status.
    """
    # Would query database
    # Simulated response
    return {
        "id": merchant_id,
        "name": "Acme Commerce",
        "slug": "acme",
        "tier": "gold",
        "status": "active",
        "industry": "electronics",
        "contact_email": "admin@acme.com",
        "gmv_mtd": 523456.78,
        "gmv_12m": 4567890.12,
        "total_customers": 12345,
        "total_orders": 45678,
        "created_at": "2023-01-15T00:00:00Z",
    }


@router.get("/me/settings")
async def get_merchant_settings(
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get merchant settings.
    
    Includes configuration for Beacon, Pulse, and Catalyst.
    """
    # Would query merchant_settings table
    return {
        "merchant_id": merchant_id,
        "beacon": {
            "enabled": True,
            "domains": ["store.acme.com", "checkout.acme.com"],
            "strict_validation": True,
        },
        "pulse": {
            "dashboard_refresh_interval": 60,
            "alert_email": "alerts@acme.com",
        },
        "catalyst": {
            "enabled": True,
            "model_version": "v2.3.1",
            "fallback_strategy": "popularity",
        },
        "notifications": {
            "email_daily_report": True,
            "slack_alerts": True,
            "slack_webhook_url": "https://hooks.slack.com/...",
        },
    }


@router.patch("/me/settings")
async def update_merchant_settings(
    settings: MerchantSettingsUpdate,
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Update merchant settings.
    
    Only provided fields are updated.
    """
    # Would update database
    return {
        "success": True,
        "updated_fields": [k for k, v in settings.dict().items() if v is not None],
    }


@router.get("/me/api-keys")
async def list_api_keys(
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    List API keys for the merchant.
    
    Keys are partially masked for security.
    """
    # Would query from secrets manager
    return {
        "api_keys": [
            {
                "id": "key_live_xxxxx",
                "name": "Production",
                "prefix": "mc_live_",
                "created_at": "2023-06-01T00:00:00Z",
                "last_used_at": "2024-01-15T12:34:56Z",
            },
            {
                "id": "key_test_xxxxx",
                "name": "Test",
                "prefix": "mc_test_",
                "created_at": "2023-06-01T00:00:00Z",
                "last_used_at": "2024-01-14T10:00:00Z",
            },
        ]
    }


@router.post("/me/api-keys")
async def create_api_key(
    name: str = Query(..., description="Key name"),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Create a new API key.
    
    The full key is only shown once upon creation.
    Store it securely!
    """
    # Would generate and store key
    return {
        "id": "key_live_new123",
        "name": name,
        "key": "mc_live_xxxxxxxxxxxxxxxxxxxx",  # Only shown once
        "created_at": "2024-01-15T00:00:00Z",
        "warning": "This key will only be shown once. Store it securely.",
    }


@router.get("/me/tier")
async def get_tier_info(
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get merchant tier information.
    
    Shows current tier, thresholds, and SLA.
    
    Tier definitions:
    - Bronze: <$100K/mo GMV, 99.5% SLA
    - Silver: $100K-$500K/mo GMV, 99.9% SLA
    - Gold: $500K-$2M/mo GMV, 99.95% SLA
    - Platinum: >$2M/mo GMV, 99.99% SLA
    """
    return {
        "current_tier": "gold",
        "gmv_mtd": 523456.78,
        "gmv_required_for_next_tier": 2000000.00,
        "next_tier": "platinum",
        "progress_percent": 26.17,
        "sla_target": 99.95,
        "features": [
            "Custom dashboards",
            "Priority support",
            "Catalyst recommendations",
            "Custom integrations",
        ],
        "tier_history": [
            {"tier": "silver", "from": "2023-01-01", "to": "2023-06-30"},
            {"tier": "gold", "from": "2023-07-01", "to": None},
        ],
    }


# Admin endpoints (internal use)
@router.get("/{merchant_id}", dependencies=[Depends(require_admin)])
async def get_merchant_by_id(merchant_id: str) -> dict[str, Any]:
    """
    Get merchant by ID (admin only).
    """
    return {"id": merchant_id, "name": "Merchant Name"}


@router.get("", dependencies=[Depends(require_admin)])
async def list_merchants(
    tier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
) -> dict[str, Any]:
    """
    List all merchants (admin only).
    """
    return {
        "merchants": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
    }
