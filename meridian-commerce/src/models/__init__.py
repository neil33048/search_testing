"""
Domain models for Meridian Commerce Platform.

These SQLAlchemy models define the core business entities:
- Customer: End consumers making purchases
- Merchant: Business accounts using the platform  
- Order: Purchase transactions
- Product: Items in merchant catalogs
- Event: Beacon tracking events

Naming conventions:
- Tables use snake_case plural (e.g., customers, orders)
- Primary keys are UUIDs with format prefix (e.g., cust_xxx, order_xxx)
- Timestamps use UTC timezone
- Soft deletes use deleted_at column
"""

from src.models.customer import Customer, CustomerTier, CustomerSegment
from src.models.merchant import Merchant, MerchantSettings
from src.models.order import Order, OrderItem, OrderStatus
from src.models.product import Product, ProductCategory
from src.models.event import Event, EventType

__all__ = [
    # Customer
    "Customer",
    "CustomerTier", 
    "CustomerSegment",
    # Merchant
    "Merchant",
    "MerchantSettings",
    # Order
    "Order",
    "OrderItem",
    "OrderStatus",
    # Product
    "Product",
    "ProductCategory",
    # Event
    "Event",
    "EventType",
]
