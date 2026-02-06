"""
Customer domain model.

Customers are end consumers who make purchases through merchant storefronts.
Each customer belongs to a single merchant and can be assigned to segments
for analytics and targeting.

Customer IDs follow the format: cust_xxxxxxxxxxxx (cust_ prefix + 12 char ID)
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
    ForeignKey,
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
    from src.models.merchant import Merchant
    from src.models.order import Order


class CustomerTier(str, enum.Enum):
    """
    Customer value tier based on lifetime value (LTV).
    
    Tiers are recalculated monthly by the Forge LTV pipeline.
    
    Legacy note: These were previously called tier1-tier4 in the old system.
    Mapping: tier1 = PLATINUM, tier2 = GOLD, tier3 = SILVER, tier4 = BRONZE
    """
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    
    @classmethod
    def from_ltv(cls, ltv: Decimal) -> "CustomerTier":
        """
        Determine tier from customer LTV.
        
        Thresholds defined in config/settings.py
        """
        # These should come from settings but hardcoded for clarity
        if ltv >= 5000:
            return cls.PLATINUM
        elif ltv >= 1000:
            return cls.GOLD
        elif ltv >= 250:
            return cls.SILVER
        else:
            return cls.BRONZE


class CustomerSegment(str, enum.Enum):
    """
    Customer behavioral segments.
    
    Assigned by the Catalyst segmentation model based on
    purchase patterns and engagement signals.
    """
    NEW = "new"                      # First purchase in last 30 days
    ACTIVE = "active"                # Purchased in last 90 days
    AT_RISK = "at_risk"              # No purchase in 90-180 days
    CHURNED = "churned"              # No purchase in 180+ days
    VIP = "vip"                      # High LTV + frequent purchaser
    BARGAIN_HUNTER = "bargain"       # Primarily buys on sale
    BRAND_LOYAL = "brand_loyal"      # Repeat purchases same brands
    EXPLORER = "explorer"            # High category diversity


def generate_customer_id() -> str:
    """Generate customer ID with cust_ prefix."""
    return f"cust_{uuid4().hex[:12]}"


class Customer(Base):
    """
    Customer entity representing an end consumer.
    
    Attributes:
        id: Unique identifier (cust_xxxxxxxxxxxx)
        merchant_id: Parent merchant
        email: Customer email (unique per merchant)
        first_name: Customer first name
        last_name: Customer last name
        tier: Value tier (Bronze/Silver/Gold/Platinum)
        segment: Behavioral segment
        ltv: Lifetime value in USD
        total_orders: Number of orders placed
        total_spent: Total amount spent in USD
        first_order_at: Timestamp of first order
        last_order_at: Timestamp of most recent order
        metadata: Flexible JSON field for custom attributes
    """
    
    __tablename__ = "customers"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        default=generate_customer_id,
    )
    
    # Merchant relationship
    merchant_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("merchants.id"),
        nullable=False,
        index=True,
    )
    
    # Contact info
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Profile
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Segmentation
    tier: Mapped[CustomerTier] = mapped_column(
        Enum(CustomerTier),
        default=CustomerTier.BRONZE,
    )
    segment: Mapped[Optional[CustomerSegment]] = mapped_column(
        Enum(CustomerSegment),
    )
    
    # Aggregated metrics (updated by Forge pipeline)
    # These are denormalized for query performance
    ltv: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    total_orders: Mapped[int] = mapped_column(default=0)
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    average_order_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    
    # Timestamps
    first_order_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_order_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Custom attributes (merchant-specific)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Marketing preferences
    accepts_marketing: Mapped[bool] = mapped_column(Boolean, default=True)
    marketing_opt_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="customers")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    
    # Indexes for common queries
    __table_args__ = (
        # Unique email per merchant
        Index("ix_customers_merchant_email", merchant_id, email, unique=True),
        # Segment queries
        Index("ix_customers_merchant_segment", merchant_id, segment),
        # Tier queries
        Index("ix_customers_merchant_tier", merchant_id, tier),
        # LTV ranking
        Index("ix_customers_merchant_ltv", merchant_id, ltv.desc()),
        # Active customer lookup
        Index(
            "ix_customers_active",
            merchant_id,
            is_active,
            postgresql_where=(deleted_at.is_(None)),
        ),
    )
    
    @property
    def full_name(self) -> str:
        """Get customer's full name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Unknown"
    
    @property
    def days_since_last_order(self) -> Optional[int]:
        """Days since last purchase."""
        if not self.last_order_at:
            return None
        delta = datetime.utcnow() - self.last_order_at.replace(tzinfo=None)
        return delta.days
    
    @property
    def is_churned(self) -> bool:
        """Check if customer is considered churned (no order in 180+ days)."""
        days = self.days_since_last_order
        return days is not None and days > 180
    
    def update_tier_from_ltv(self) -> None:
        """Recalculate tier based on current LTV."""
        self.tier = CustomerTier.from_ltv(self.ltv)
    
    def __repr__(self) -> str:
        return f"<Customer {self.id} ({self.email})>"
