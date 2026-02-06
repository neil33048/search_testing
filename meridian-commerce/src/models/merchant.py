"""
Merchant domain model.

Merchants are business accounts that use the Meridian Commerce platform.
Each merchant has their own customers, products, and orders.

Merchant IDs follow the format: merch_xxxxxxxxxxxx (merch_ prefix + 12 char ID)

Merchant tiers (Bronze/Silver/Gold/Platinum) determine:
- SLA commitments
- Feature access
- Rate limits
- Support level
"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.customer import Customer
    from src.models.order import Order
    from src.models.product import Product


class MerchantTier(str, enum.Enum):
    """
    Merchant tier based on GMV (Gross Merchandise Value).
    
    Tiers determine SLA, feature access, and pricing.
    See docs/merchant_tiers.md for detailed breakdown.
    
    Legacy mapping: tier1=PLATINUM, tier2=GOLD, tier3=SILVER, tier4=BRONZE
    """
    BRONZE = "bronze"      # <$100K/mo GMV
    SILVER = "silver"      # $100K-$500K/mo GMV
    GOLD = "gold"          # $500K-$2M/mo GMV
    PLATINUM = "platinum"  # >$2M/mo GMV
    
    @property
    def sla_target(self) -> float:
        """SLA uptime target for this tier."""
        sla_map = {
            MerchantTier.BRONZE: 99.5,
            MerchantTier.SILVER: 99.9,
            MerchantTier.GOLD: 99.95,
            MerchantTier.PLATINUM: 99.99,
        }
        return sla_map[self]
    
    @property
    def rate_limit_multiplier(self) -> int:
        """Rate limit multiplier vs base limits."""
        multiplier_map = {
            MerchantTier.BRONZE: 1,
            MerchantTier.SILVER: 2,
            MerchantTier.GOLD: 5,
            MerchantTier.PLATINUM: 10,
        }
        return multiplier_map[self]


class MerchantStatus(str, enum.Enum):
    """Merchant account status."""
    PENDING = "pending"        # Awaiting verification
    ACTIVE = "active"          # Normal operation
    SUSPENDED = "suspended"    # Temporarily disabled
    CHURNED = "churned"        # Closed account


class MerchantIndustry(str, enum.Enum):
    """
    Merchant industry vertical.
    
    Used for benchmarking and industry-specific features.
    """
    APPAREL = "apparel"
    ELECTRONICS = "electronics"
    HOME_GARDEN = "home_garden"
    BEAUTY = "beauty"
    FOOD_BEVERAGE = "food_beverage"
    HEALTH_WELLNESS = "health_wellness"
    SPORTS_OUTDOORS = "sports_outdoors"
    TOYS_GAMES = "toys_games"
    AUTOMOTIVE = "automotive"
    OTHER = "other"


def generate_merchant_id() -> str:
    """Generate merchant ID with merch_ prefix."""
    return f"merch_{uuid4().hex[:12]}"


class Merchant(Base):
    """
    Merchant entity representing a business account.
    
    Merchants subscribe to the Meridian platform to power their
    e-commerce analytics and recommendations.
    
    Attributes:
        id: Unique identifier (merch_xxxxxxxxxxxx)
        name: Business name
        slug: URL-friendly identifier
        tier: Service tier (Bronze/Silver/Gold/Platinum)
        industry: Business vertical
        status: Account status
        gmv_mtd: Month-to-date GMV
        gmv_12m: Rolling 12-month GMV
    """
    
    __tablename__ = "merchants"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        default=generate_merchant_id,
    )
    
    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    
    # Classification
    tier: Mapped[MerchantTier] = mapped_column(
        Enum(MerchantTier),
        default=MerchantTier.BRONZE,
    )
    industry: Mapped[Optional[MerchantIndustry]] = mapped_column(Enum(MerchantIndustry))
    status: Mapped[MerchantStatus] = mapped_column(
        Enum(MerchantStatus),
        default=MerchantStatus.PENDING,
    )
    
    # Contact
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    website_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Business details
    company_legal_name: Mapped[Optional[str]] = mapped_column(String(255))
    tax_id: Mapped[Optional[str]] = mapped_column(String(50))
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country_code: Mapped[str] = mapped_column(String(2), default="US")
    
    # Aggregated metrics (updated by Forge pipeline)
    gmv_mtd: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        comment="Month-to-date GMV",
    )
    gmv_12m: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        comment="Rolling 12-month GMV",
    )
    total_customers: Mapped[int] = mapped_column(default=0)
    total_orders: Mapped[int] = mapped_column(default=0)
    total_products: Mapped[int] = mapped_column(default=0)
    
    # ARPU metrics
    arpu_30d: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        comment="30-day Average Revenue Per User",
    )
    
    # Settings (stored as JSON for flexibility)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Feature flags (merchant-specific overrides)
    features: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Feature flags and limits for this merchant",
    )
    
    # Integration config
    # API keys are stored in secrets manager, only key IDs stored here
    api_key_id: Mapped[Optional[str]] = mapped_column(String(100))
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Billing
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100))
    billing_email: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Support
    # Platinum merchants get a dedicated CSM (Customer Success Manager)
    csm_user_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Assigned Customer Success Manager",
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="When merchant completed onboarding",
    )
    churned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")
    orders: Mapped[list["Order"]] = relationship(back_populates="merchant")
    products: Mapped[list["Product"]] = relationship(back_populates="merchant")
    
    # Indexes
    __table_args__ = (
        Index("ix_merchants_status_tier", status, tier),
        Index("ix_merchants_industry", industry),
        Index("ix_merchants_gmv_12m", gmv_12m.desc()),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if merchant is in active status."""
        return self.status == MerchantStatus.ACTIVE
    
    @property
    def is_enterprise(self) -> bool:
        """Check if merchant is enterprise tier (Gold or Platinum)."""
        return self.tier in (MerchantTier.GOLD, MerchantTier.PLATINUM)
    
    def get_feature(self, feature_name: str, default: bool = False) -> bool:
        """
        Check if a feature is enabled for this merchant.
        
        Checks merchant-specific overrides first, then defaults.
        """
        return self.features.get(feature_name, default)
    
    def update_tier_from_gmv(self) -> None:
        """
        Recalculate tier based on 12-month GMV.
        
        Called by Forge pipeline after GMV aggregation.
        """
        gmv = self.gmv_12m / 12  # Convert to monthly average
        
        if gmv >= 2_000_000:
            self.tier = MerchantTier.PLATINUM
        elif gmv >= 500_000:
            self.tier = MerchantTier.GOLD
        elif gmv >= 100_000:
            self.tier = MerchantTier.SILVER
        else:
            self.tier = MerchantTier.BRONZE
    
    def __repr__(self) -> str:
        return f"<Merchant {self.id} ({self.name})>"


class MerchantSettings(Base):
    """
    Extended merchant settings stored separately for performance.
    
    Contains verbose configuration that isn't needed for most queries.
    """
    
    __tablename__ = "merchant_settings"
    
    merchant_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("merchants.id"),
        primary_key=True,
    )
    
    # Beacon settings
    beacon_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    beacon_domains: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        comment="Allowed domains for Beacon tracking",
    )
    
    # Pulse settings
    pulse_dashboard_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Custom dashboard layout and widgets",
    )
    pulse_alerts_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Alert thresholds and notification settings",
    )
    
    # Catalyst settings
    catalyst_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    catalyst_model_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Recommendation model parameters",
    )
    catalyst_ab_test_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Active A/B test configurations",
    )
    
    # Notification preferences
    email_notifications: Mapped[dict] = mapped_column(JSONB, default=dict)
    slack_webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    pagerduty_key: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Branding
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    primary_color: Mapped[Optional[str]] = mapped_column(String(7))  # Hex color
    
    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
