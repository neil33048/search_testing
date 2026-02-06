"""
Event domain model for Beacon event tracking.

Events are behavioral signals collected from merchant storefronts via
the Beacon tracking system. They power:
- Pulse real-time analytics
- Catalyst recommendation training
- Funnel analysis and attribution

Event IDs follow the format: evt_xxxxxxxxxxxxxxxxxx (evt_ prefix + 18 char ID)

Events are high-volume - we process 50M+ events/day across all merchants.
They are stored in ClickHouse for real-time queries and archived to S3/Snowflake
for historical analysis.
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class EventType(str, enum.Enum):
    """
    Beacon event types.
    
    Events are categorized by type for processing and analysis.
    New event types must be registered in src/beacon/schemas.py
    with their validation schema.
    """
    
    # Page events
    PAGE_VIEW = "page_view"
    PAGE_EXIT = "page_exit"
    
    # Product events
    PRODUCT_VIEW = "product_view"
    PRODUCT_CLICK = "product_click"
    PRODUCT_IMPRESSION = "product_impression"
    QUICK_VIEW = "quick_view"
    
    # Cart events
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    CART_VIEW = "cart_view"
    UPDATE_CART_QUANTITY = "update_cart_quantity"
    
    # Checkout events
    BEGIN_CHECKOUT = "begin_checkout"
    ADD_SHIPPING_INFO = "add_shipping_info"
    ADD_PAYMENT_INFO = "add_payment_info"
    CHECKOUT_STEP = "checkout_step"
    
    # Purchase events
    PURCHASE = "purchase"
    REFUND = "refund"
    
    # Search events
    SEARCH = "search"
    SEARCH_CLICK = "search_click"
    
    # User events
    SIGN_UP = "sign_up"
    LOGIN = "login"
    LOGOUT = "logout"
    
    # Engagement events
    WISHLIST_ADD = "wishlist_add"
    WISHLIST_REMOVE = "wishlist_remove"
    SHARE = "share"
    REVIEW_SUBMIT = "review_submit"
    
    # Recommendation events (Catalyst)
    RECOMMENDATION_VIEW = "recommendation_view"
    RECOMMENDATION_CLICK = "recommendation_click"
    
    # Custom events (merchant-defined)
    CUSTOM = "custom"
    
    @property
    def is_conversion_event(self) -> bool:
        """Check if this is a conversion event."""
        return self in (
            EventType.PURCHASE,
            EventType.SIGN_UP,
            EventType.ADD_TO_CART,
        )
    
    @property
    def is_engagement_event(self) -> bool:
        """Check if this is an engagement event."""
        return self in (
            EventType.PRODUCT_VIEW,
            EventType.PRODUCT_CLICK,
            EventType.SEARCH,
            EventType.WISHLIST_ADD,
        )


class EventSource(str, enum.Enum):
    """Source of the event."""
    WEB = "web"              # Browser JavaScript SDK
    MOBILE_IOS = "ios"       # iOS SDK
    MOBILE_ANDROID = "android"  # Android SDK
    SERVER = "server"        # Server-side API
    IMPORT = "import"        # Historical data import


def generate_event_id() -> str:
    """Generate event ID with evt_ prefix."""
    return f"evt_{uuid4().hex[:18]}"


class Event(Base):
    """
    Beacon event entity.
    
    Events are behavioral signals from merchant storefronts.
    This table is for PostgreSQL storage; production events
    go to ClickHouse via Kinesis.
    
    Attributes:
        id: Unique identifier (evt_xxxxxxxxxxxxxxxxxx)
        merchant_id: Source merchant
        event_type: Type of event (page_view, purchase, etc.)
        session_id: Browser/app session ID
        user_id: Logged-in user ID (if available)
        anonymous_id: Anonymous visitor ID
        properties: Event-specific data (JSON)
        context: Device/browser/location context (JSON)
        timestamp: When event occurred (client time)
        received_at: When event was received by Beacon
    """
    
    __tablename__ = "events"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(25),
        primary_key=True,
        default=generate_event_id,
    )
    
    # Merchant
    merchant_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    
    # Event type
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType),
        nullable=False,
    )
    event_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Custom event name (for CUSTOM type)",
    )
    
    # User identification
    # At least one of user_id or anonymous_id should be present
    user_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        index=True,
        comment="Logged-in user identifier",
    )
    anonymous_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Anonymous visitor ID (from cookie/device)",
    )
    
    # Session tracking
    session_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Browser/app session ID",
    )
    
    # Event source
    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource),
        default=EventSource.WEB,
    )
    
    # Event properties (event-specific data)
    # Structure depends on event_type
    # Example for product_view: {"product_id": "prod_xxx", "price": 29.99}
    properties: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Event-specific properties",
    )
    
    # Context (device, browser, location info)
    # Captured by Beacon SDK
    context: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Device/browser/location context",
    )
    
    # Page information
    page_url: Mapped[Optional[str]] = mapped_column(Text)
    page_path: Mapped[Optional[str]] = mapped_column(String(500))
    page_title: Mapped[Optional[str]] = mapped_column(String(500))
    referrer: Mapped[Optional[str]] = mapped_column(Text)
    
    # UTM parameters (for attribution)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100))
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100))
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100))
    utm_term: Mapped[Optional[str]] = mapped_column(String(100))
    utm_content: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Device info (extracted from context for indexing)
    device_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="desktop, mobile, tablet",
    )
    browser: Mapped[Optional[str]] = mapped_column(String(50))
    os: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Location (from IP geolocation)
    country_code: Mapped[Optional[str]] = mapped_column(String(2))
    region: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Timestamps
    # timestamp = when event occurred (client time, may be unreliable)
    # received_at = when Beacon received the event (server time, authoritative)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Client-reported event time",
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Server receive time",
    )
    
    # Processing metadata
    processed: Mapped[bool] = mapped_column(
        default=False,
        comment="Has event been processed by Forge",
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Indexes optimized for common query patterns
    __table_args__ = (
        # Time-based queries (most common)
        Index("ix_events_merchant_time", merchant_id, received_at.desc()),
        
        # User journey analysis
        Index("ix_events_merchant_session", merchant_id, session_id, received_at),
        
        # Event type analysis
        Index("ix_events_merchant_type_time", merchant_id, event_type, received_at.desc()),
        
        # Funnel analysis (conversion events)
        Index(
            "ix_events_conversions",
            merchant_id,
            event_type,
            received_at,
            postgresql_where=(event_type.in_([
                EventType.PURCHASE,
                EventType.ADD_TO_CART,
                EventType.BEGIN_CHECKOUT,
            ])),
        ),
        
        # Partitioning hint (for TimescaleDB or partitioned tables)
        # In production, this table would be partitioned by received_at
        {"postgresql_partition_by": "RANGE (received_at)"},
    )
    
    @property
    def is_identified(self) -> bool:
        """Check if event has a logged-in user."""
        return self.user_id is not None
    
    @property
    def product_id(self) -> Optional[str]:
        """Extract product_id from properties if present."""
        return self.properties.get("product_id")
    
    @property
    def order_id(self) -> Optional[str]:
        """Extract order_id from properties if present."""
        return self.properties.get("order_id")
    
    @property
    def revenue(self) -> Optional[float]:
        """Extract revenue from properties if present."""
        return self.properties.get("revenue") or self.properties.get("value")
    
    def __repr__(self) -> str:
        return f"<Event {self.id} ({self.event_type.value})>"


# ClickHouse table definition for reference
# This is the actual production table schema
CLICKHOUSE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id String,
    merchant_id String,
    event_type String,
    event_name Nullable(String),
    user_id Nullable(String),
    anonymous_id String,
    session_id String,
    source String,
    properties String,  -- JSON string
    context String,     -- JSON string
    page_url Nullable(String),
    page_path Nullable(String),
    utm_source Nullable(String),
    utm_medium Nullable(String),
    utm_campaign Nullable(String),
    device_type Nullable(String),
    browser Nullable(String),
    os Nullable(String),
    country_code Nullable(String),
    region Nullable(String),
    city Nullable(String),
    timestamp DateTime64(3),
    received_at DateTime64(3),
    date Date MATERIALIZED toDate(received_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(received_at)
ORDER BY (merchant_id, received_at, event_type)
TTL received_at + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
"""
