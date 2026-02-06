"""
Product domain model.

Products are items sold by merchants through their storefronts.
Products can be organized into categories and have multiple variants.

Product IDs follow the format: prod_xxxxxxxxxxxx (prod_ prefix + 12 char ID)

Products are used by:
- Beacon: Product view/cart events
- Catalyst: Recommendation training data
- Pulse: Product performance analytics
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.merchant import Merchant


class ProductStatus(str, enum.Enum):
    """Product availability status."""
    DRAFT = "draft"        # Not visible to customers
    ACTIVE = "active"      # Available for purchase
    ARCHIVED = "archived"  # Hidden but preserved


class InventoryPolicy(str, enum.Enum):
    """How inventory is managed."""
    TRACK = "track"          # Track inventory levels
    CONTINUE = "continue"    # Continue selling when out of stock
    DENY = "deny"            # Stop selling when out of stock


def generate_product_id() -> str:
    """Generate product ID with prod_ prefix."""
    return f"prod_{uuid4().hex[:12]}"


class Product(Base):
    """
    Product entity representing an item in a merchant's catalog.
    
    Products have:
    - Basic info (name, description, SKU)
    - Pricing (can have sale price)
    - Categories (hierarchical)
    - Inventory tracking
    - Catalyst embeddings for recommendations
    
    Attributes:
        id: Unique identifier (prod_xxxxxxxxxxxx)
        merchant_id: Owning merchant
        name: Product name
        sku: Stock keeping unit
        price: Regular price
        sale_price: Discounted price (if on sale)
        category_path: Category hierarchy (e.g., "Apparel > Men > Shirts")
    """
    
    __tablename__ = "products"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        default=generate_product_id,
    )
    
    # Merchant relationship
    merchant_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("merchants.id"),
        nullable=False,
        index=True,
    )
    
    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(String(100))
    barcode: Mapped[Optional[str]] = mapped_column(String(100))  # UPC, EAN, etc.
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text)
    short_description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Status
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus),
        default=ProductStatus.DRAFT,
    )
    
    # Pricing
    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        comment="Original price (for showing discount)",
    )
    sale_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        comment="Cost of goods sold (for margin calculations)",
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    
    # Category (hierarchical path stored as string)
    # Example: "Electronics > Computers > Laptops"
    category_path: Mapped[Optional[str]] = mapped_column(String(500))
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("product_categories.id"),
    )
    
    # Tags for filtering and search
    tags: Mapped[list] = mapped_column(ARRAY(String(50)), default=list)
    
    # Brand
    brand: Mapped[Optional[str]] = mapped_column(String(100))
    vendor: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Inventory
    inventory_policy: Mapped[InventoryPolicy] = mapped_column(
        Enum(InventoryPolicy),
        default=InventoryPolicy.DENY,
    )
    inventory_quantity: Mapped[int] = mapped_column(Integer, default=0)
    inventory_reserved: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Units reserved in pending orders",
    )
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    
    # Physical attributes (for shipping)
    weight_grams: Mapped[Optional[int]] = mapped_column(Integer)
    length_cm: Mapped[Optional[int]] = mapped_column(Integer)
    width_cm: Mapped[Optional[int]] = mapped_column(Integer)
    height_cm: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Media
    # Primary image URL
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    # Additional images as JSON array
    images: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        comment="List of image URLs",
    )
    
    # Variants (stored as JSON for flexibility)
    # Example: [{"name": "Size", "values": ["S", "M", "L"]}, ...]
    variant_options: Mapped[list] = mapped_column(JSONB, default=list)
    has_variants: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # SEO
    meta_title: Mapped[Optional[str]] = mapped_column(String(100))
    meta_description: Mapped[Optional[str]] = mapped_column(String(300))
    
    # Full-text search vector
    # Updated via trigger
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)
    
    # Analytics metrics (updated by Forge pipeline)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
    )
    conversion_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        comment="Orders / Views ratio",
    )
    
    # Catalyst embeddings
    # Vector representation for similarity search
    # Stored in separate table for performance, referenced here
    embedding_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="Version of embedding model used",
    )
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
    )
    
    # Custom attributes (merchant-defined)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Visibility
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    
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
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="products")
    category: Mapped[Optional["ProductCategory"]] = relationship(back_populates="products")
    
    # Indexes
    __table_args__ = (
        Index("ix_products_merchant_status", merchant_id, status),
        Index("ix_products_merchant_category", merchant_id, category_id),
        Index("ix_products_merchant_sku", merchant_id, sku),
        Index("ix_products_merchant_brand", merchant_id, brand),
        # Full-text search
        Index(
            "ix_products_search",
            search_vector,
            postgresql_using="gin",
        ),
        # Popular products
        Index("ix_products_merchant_orders", merchant_id, order_count.desc()),
        # Tag filtering
        Index(
            "ix_products_tags",
            tags,
            postgresql_using="gin",
        ),
    )
    
    @property
    def current_price(self) -> Decimal:
        """Get effective price (sale price if available)."""
        return self.sale_price or self.price
    
    @property
    def is_on_sale(self) -> bool:
        """Check if product is on sale."""
        return self.sale_price is not None and self.sale_price < self.price
    
    @property
    def discount_percentage(self) -> Optional[int]:
        """Get discount percentage if on sale."""
        if not self.is_on_sale:
            return None
        return int(100 * (1 - self.sale_price / self.price))
    
    @property
    def is_in_stock(self) -> bool:
        """Check if product is in stock."""
        if self.inventory_policy == InventoryPolicy.CONTINUE:
            return True
        available = self.inventory_quantity - self.inventory_reserved
        return available > 0
    
    @property
    def available_quantity(self) -> int:
        """Get quantity available for sale."""
        return max(0, self.inventory_quantity - self.inventory_reserved)
    
    @property
    def is_low_stock(self) -> bool:
        """Check if inventory is below threshold."""
        return self.available_quantity <= self.low_stock_threshold
    
    @property
    def margin(self) -> Optional[Decimal]:
        """Calculate profit margin percentage."""
        if not self.cost_price or self.cost_price == 0:
            return None
        return (self.current_price - self.cost_price) / self.current_price * 100
    
    def __repr__(self) -> str:
        return f"<Product {self.id} ({self.name})>"


class ProductCategory(Base):
    """
    Product category with hierarchical structure.
    
    Categories form a tree structure using materialized path pattern.
    Example: Electronics > Computers > Laptops
    
    Each merchant has their own category tree.
    """
    
    __tablename__ = "product_categories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    merchant_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("merchants.id"),
        nullable=False,
    )
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Parent category (null for root categories)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("product_categories.id"),
    )
    
    # Materialized path for efficient tree queries
    # Example: "/1/5/12/" for category 12 under 5 under 1
    path: Mapped[str] = mapped_column(String(255), default="/")
    
    # Tree depth (0 = root)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    
    # Display order among siblings
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Category image
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Product count (denormalized for performance)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # SEO
    description: Mapped[Optional[str]] = mapped_column(Text)
    meta_title: Mapped[Optional[str]] = mapped_column(String(100))
    meta_description: Mapped[Optional[str]] = mapped_column(String(300))
    
    # Visibility
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    
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
    
    # Relationships
    parent: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory",
        remote_side=[id],
        backref="children",
    )
    products: Mapped[list["Product"]] = relationship(back_populates="category")
    
    __table_args__ = (
        Index("ix_categories_merchant_parent", merchant_id, parent_id),
        Index("ix_categories_merchant_path", merchant_id, path),
        Index("ix_categories_merchant_slug", merchant_id, slug, unique=True),
    )
    
    @property
    def full_path(self) -> str:
        """Get full category path as readable string."""
        # This would typically be resolved via query
        # Placeholder implementation
        return self.name
    
    def __repr__(self) -> str:
        return f"<ProductCategory {self.id} ({self.name})>"
