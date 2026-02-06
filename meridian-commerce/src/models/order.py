"""
Order domain model.

Orders represent purchase transactions made by customers.
Each order belongs to a merchant and customer, and contains line items.

Order IDs follow the format: order_xxxxxxxxxxxx (order_ prefix + 12 char ID)

Order lifecycle:
1. PENDING - Order created, awaiting payment
2. CONFIRMED - Payment successful
3. PROCESSING - Being prepared/shipped
4. SHIPPED - In transit
5. DELIVERED - Successfully delivered
6. CANCELLED - Order cancelled
7. REFUNDED - Fully refunded
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
    Integer,
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
    from src.models.merchant import Merchant
    from src.models.product import Product


class OrderStatus(str, enum.Enum):
    """Order lifecycle status."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    
    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state."""
        return self in (
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        )
    
    @property
    def is_active(self) -> bool:
        """Check if order is still active (not terminal)."""
        return not self.is_terminal


class PaymentMethod(str, enum.Enum):
    """Payment method used for order."""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    BANK_TRANSFER = "bank_transfer"
    BUY_NOW_PAY_LATER = "bnpl"  # Klarna, Affirm, etc.
    STORE_CREDIT = "store_credit"
    OTHER = "other"


class FulfillmentMethod(str, enum.Enum):
    """Order fulfillment method."""
    SHIP = "ship"
    PICKUP = "pickup"
    DIGITAL = "digital"  # Digital products


def generate_order_id() -> str:
    """Generate order ID with order_ prefix."""
    return f"order_{uuid4().hex[:12]}"


class Order(Base):
    """
    Order entity representing a purchase transaction.
    
    Attributes:
        id: Unique identifier (order_xxxxxxxxxxxx)
        merchant_id: Merchant who received the order
        customer_id: Customer who placed the order
        status: Current order status
        total_amount: Order total including tax and shipping
        subtotal: Sum of line items before tax/shipping
        tax_amount: Tax charged
        shipping_amount: Shipping cost
        discount_amount: Total discounts applied
        currency: ISO currency code (default USD)
    """
    
    __tablename__ = "orders"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        default=generate_order_id,
    )
    
    # External reference (merchant's order number)
    # Some merchants have their own order numbering system
    external_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Relationships
    merchant_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("merchants.id"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )
    
    # Status
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        default=OrderStatus.PENDING,
    )
    
    # Amounts (all in cents to avoid float precision issues)
    # Display amounts are calculated as amount / 100
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    shipping_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    
    # Currency (ISO 4217)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    
    # Item counts
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_item_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Payment
    payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(Enum(PaymentMethod))
    payment_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="External payment ID (Stripe, PayPal, etc.)",
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Fulfillment
    fulfillment_method: Mapped[FulfillmentMethod] = mapped_column(
        Enum(FulfillmentMethod),
        default=FulfillmentMethod.SHIP,
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))
    carrier: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Shipping address (denormalized for performance)
    shipping_first_name: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_last_name: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    shipping_address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    shipping_city: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_state: Mapped[Optional[str]] = mapped_column(String(100))
    shipping_postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    shipping_country_code: Mapped[Optional[str]] = mapped_column(String(2))
    
    # Billing address
    billing_address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    billing_city: Mapped[Optional[str]] = mapped_column(String(100))
    billing_postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    billing_country_code: Mapped[Optional[str]] = mapped_column(String(2))
    
    # Discounts
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Attribution (for analytics)
    # These are populated by Beacon from the session context
    source: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Traffic source (google, facebook, direct, etc.)",
    )
    medium: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Marketing medium (cpc, email, organic, etc.)",
    )
    campaign: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Campaign name",
    )
    landing_page: Mapped[Optional[str]] = mapped_column(Text)
    
    # Recommendations attribution
    # Did any items come from Catalyst recommendations?
    has_recommended_items: Mapped[bool] = mapped_column(Boolean, default=False)
    recommended_items_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        comment="Revenue from recommended items",
    )
    
    # Notes
    customer_notes: Mapped[Optional[str]] = mapped_column(Text)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Refund info
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    refund_reason: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Risk scoring
    # Populated by fraud detection system
    risk_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Fraud risk score 0-100",
    )
    risk_flags: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        comment="Risk indicators",
    )
    
    # Metadata
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
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
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="orders")
    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )
    
    # Indexes
    __table_args__ = (
        # Primary query patterns
        Index("ix_orders_merchant_created", merchant_id, created_at.desc()),
        Index("ix_orders_customer_created", customer_id, created_at.desc()),
        Index("ix_orders_merchant_status", merchant_id, status),
        
        # Date-based analytics
        Index("ix_orders_merchant_date", merchant_id, func.date(created_at)),
        
        # External ID lookup (for merchant integrations)
        Index("ix_orders_merchant_external", merchant_id, external_id),
        
        # GMV calculations
        Index("ix_orders_merchant_total", merchant_id, total_amount),
    )
    
    @property
    def net_amount(self) -> Decimal:
        """Order total minus refunds."""
        return self.total_amount - self.refund_amount
    
    @property
    def is_fully_refunded(self) -> bool:
        """Check if order is fully refunded."""
        return self.refund_amount >= self.total_amount
    
    @property
    def gmv(self) -> Decimal:
        """
        Gross Merchandise Value for this order.
        
        GMV = subtotal (excludes tax and shipping)
        Used for merchant tier calculations.
        """
        return self.subtotal
    
    def calculate_totals(self) -> None:
        """Recalculate order totals from line items."""
        self.subtotal = sum(item.total_price for item in self.items)
        self.item_count = sum(item.quantity for item in self.items)
        self.unique_item_count = len(self.items)
        self.total_amount = (
            self.subtotal
            + self.tax_amount
            + self.shipping_amount
            - self.discount_amount
        )
    
    def __repr__(self) -> str:
        return f"<Order {self.id} ({self.status.value})>"


class OrderItem(Base):
    """
    Order line item.
    
    Represents a single product in an order with quantity and pricing.
    Prices are captured at time of order (product prices may change later).
    """
    
    __tablename__ = "order_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    order_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("orders.id"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("products.id"),
        nullable=False,
    )
    
    # Product snapshot at time of order
    # Stored for historical accuracy even if product is deleted/changed
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_sku: Mapped[Optional[str]] = mapped_column(String(100))
    product_variant: Mapped[Optional[str]] = mapped_column(
        String(255),
        comment="Variant info (size, color, etc.)",
    )
    
    # Pricing
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    
    # Discounts applied to this item
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
    )
    
    # Was this item recommended by Catalyst?
    from_recommendation: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation_source: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Which rec model served this (pdp, cart, email, etc.)",
    )
    
    # Fulfillment status (for partial shipments)
    quantity_fulfilled: Mapped[int] = mapped_column(Integer, default=0)
    quantity_refunded: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    
    __table_args__ = (
        Index("ix_order_items_order", order_id),
        Index("ix_order_items_product", product_id),
    )
    
    @property
    def net_quantity(self) -> int:
        """Quantity minus refunded."""
        return self.quantity - self.quantity_refunded
    
    def __repr__(self) -> str:
        return f"<OrderItem {self.product_name} x{self.quantity}>"
