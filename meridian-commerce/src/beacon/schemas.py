"""
Beacon Event Schemas

Defines the expected structure for each event type.
These schemas are used for validation and documentation.

Schema format inspired by JSON Schema but simplified for our needs.
Merchants can define custom event types with their own schemas.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from src.models.event import EventType


@dataclass
class EventSchema:
    """
    Schema definition for a Beacon event type.
    
    Attributes:
        event_type: The event type this schema applies to
        description: Human-readable description
        required_fields: Fields that must be present
        field_types: Expected type for each field
        constraints: Additional constraints (min, max, enum, pattern)
        examples: Example payloads for documentation
    """
    
    event_type: EventType
    description: str
    required_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    field_types: dict[str, str] = field(default_factory=dict)
    constraints: dict[str, dict[str, Any]] = field(default_factory=dict)
    examples: list[dict] = field(default_factory=list)
    
    # Metadata
    version: str = "1.0"
    deprecated: bool = False
    deprecation_message: Optional[str] = None


# =============================================================================
# Event Schema Definitions
# =============================================================================

PAGE_VIEW_SCHEMA = EventSchema(
    event_type=EventType.PAGE_VIEW,
    description="Fired when a user views a page",
    required_fields=["page_path"],
    optional_fields=["page_title", "page_url", "referrer"],
    field_types={
        "page_path": "string",
        "page_title": "string",
        "page_url": "string",
        "referrer": "string",
    },
    constraints={
        "page_path": {"max_length": 500},
        "page_title": {"max_length": 500},
        "page_url": {"max_length": 2000},
    },
    examples=[
        {
            "page_path": "/products/blue-widget",
            "page_title": "Blue Widget - Acme Store",
            "page_url": "https://store.example.com/products/blue-widget",
        }
    ],
)

PRODUCT_VIEW_SCHEMA = EventSchema(
    event_type=EventType.PRODUCT_VIEW,
    description="Fired when a user views a product detail page",
    required_fields=["product_id"],
    optional_fields=[
        "product_name",
        "product_sku",
        "price",
        "currency",
        "category",
        "brand",
        "variant",
        "position",  # For product lists
    ],
    field_types={
        "product_id": "string",
        "product_name": "string",
        "product_sku": "string",
        "price": "number",
        "currency": "string",
        "category": "string",
        "brand": "string",
        "variant": "string",
        "position": "integer",
    },
    constraints={
        "product_id": {"max_length": 50},
        "price": {"min": 0},
        "currency": {"max_length": 3},
        "position": {"min": 1},
    },
    examples=[
        {
            "product_id": "prod_abc123def456",
            "product_name": "Blue Widget",
            "price": 29.99,
            "currency": "USD",
            "category": "Widgets > Blue",
            "brand": "Acme",
        }
    ],
)

ADD_TO_CART_SCHEMA = EventSchema(
    event_type=EventType.ADD_TO_CART,
    description="Fired when a user adds an item to their cart",
    required_fields=["product_id", "quantity"],
    optional_fields=[
        "product_name",
        "price",
        "currency",
        "variant",
        "cart_id",
    ],
    field_types={
        "product_id": "string",
        "quantity": "integer",
        "product_name": "string",
        "price": "number",
        "currency": "string",
        "variant": "string",
        "cart_id": "string",
    },
    constraints={
        "product_id": {"max_length": 50},
        "quantity": {"min": 1, "max": 1000},
        "price": {"min": 0},
    },
    examples=[
        {
            "product_id": "prod_abc123def456",
            "quantity": 2,
            "product_name": "Blue Widget",
            "price": 29.99,
            "currency": "USD",
            "variant": "Large",
        }
    ],
)

REMOVE_FROM_CART_SCHEMA = EventSchema(
    event_type=EventType.REMOVE_FROM_CART,
    description="Fired when a user removes an item from their cart",
    required_fields=["product_id"],
    optional_fields=["quantity", "cart_id"],
    field_types={
        "product_id": "string",
        "quantity": "integer",
        "cart_id": "string",
    },
    constraints={
        "product_id": {"max_length": 50},
        "quantity": {"min": 1},
    },
)

BEGIN_CHECKOUT_SCHEMA = EventSchema(
    event_type=EventType.BEGIN_CHECKOUT,
    description="Fired when a user initiates checkout",
    required_fields=["cart_id"],
    optional_fields=[
        "value",
        "currency",
        "item_count",
        "coupon",
    ],
    field_types={
        "cart_id": "string",
        "value": "number",
        "currency": "string",
        "item_count": "integer",
        "coupon": "string",
    },
    constraints={
        "value": {"min": 0},
        "item_count": {"min": 1},
    },
)

PURCHASE_SCHEMA = EventSchema(
    event_type=EventType.PURCHASE,
    description="Fired when a purchase is completed",
    required_fields=["order_id", "revenue"],
    optional_fields=[
        "currency",
        "tax",
        "shipping",
        "coupon",
        "items",
        "payment_method",
    ],
    field_types={
        "order_id": "string",
        "revenue": "number",
        "currency": "string",
        "tax": "number",
        "shipping": "number",
        "coupon": "string",
        "items": "array",
        "payment_method": "string",
    },
    constraints={
        "order_id": {"max_length": 50},
        "revenue": {"min": 0},
        "tax": {"min": 0},
        "shipping": {"min": 0},
    },
    examples=[
        {
            "order_id": "order_xyz789",
            "revenue": 89.97,
            "currency": "USD",
            "tax": 8.10,
            "shipping": 5.99,
            "items": [
                {"product_id": "prod_abc123", "quantity": 3, "price": 29.99}
            ],
        }
    ],
)

SEARCH_SCHEMA = EventSchema(
    event_type=EventType.SEARCH,
    description="Fired when a user performs a search",
    required_fields=["query"],
    optional_fields=[
        "result_count",
        "filters",
        "sort",
        "page",
    ],
    field_types={
        "query": "string",
        "result_count": "integer",
        "filters": "object",
        "sort": "string",
        "page": "integer",
    },
    constraints={
        "query": {"max_length": 500},
        "result_count": {"min": 0},
        "page": {"min": 1},
    },
    examples=[
        {
            "query": "blue widgets",
            "result_count": 42,
            "filters": {"color": "blue", "price_max": 50},
            "sort": "relevance",
        }
    ],
)

SEARCH_CLICK_SCHEMA = EventSchema(
    event_type=EventType.SEARCH_CLICK,
    description="Fired when a user clicks a search result",
    required_fields=["query", "product_id", "position"],
    optional_fields=["result_count"],
    field_types={
        "query": "string",
        "product_id": "string",
        "position": "integer",
        "result_count": "integer",
    },
    constraints={
        "position": {"min": 1},
    },
)

RECOMMENDATION_VIEW_SCHEMA = EventSchema(
    event_type=EventType.RECOMMENDATION_VIEW,
    description="Fired when recommendations are displayed to a user",
    required_fields=["placement", "product_ids"],
    optional_fields=[
        "model_version",
        "strategy",
        "source_product_id",
    ],
    field_types={
        "placement": "string",
        "product_ids": "array",
        "model_version": "string",
        "strategy": "string",
        "source_product_id": "string",
    },
    constraints={
        "placement": {
            "enum": ["pdp", "cart", "homepage", "category", "email", "checkout"]
        },
        "strategy": {
            "enum": ["collaborative", "content_based", "popularity", "hybrid"]
        },
    },
    examples=[
        {
            "placement": "pdp",
            "product_ids": ["prod_abc", "prod_def", "prod_ghi"],
            "model_version": "v2.3.1",
            "strategy": "collaborative",
            "source_product_id": "prod_xyz",
        }
    ],
)

RECOMMENDATION_CLICK_SCHEMA = EventSchema(
    event_type=EventType.RECOMMENDATION_CLICK,
    description="Fired when a user clicks a recommended product",
    required_fields=["placement", "product_id", "position"],
    optional_fields=[
        "model_version",
        "strategy",
        "source_product_id",
    ],
    field_types={
        "placement": "string",
        "product_id": "string",
        "position": "integer",
        "model_version": "string",
        "strategy": "string",
        "source_product_id": "string",
    },
    constraints={
        "position": {"min": 1},
    },
)

SIGN_UP_SCHEMA = EventSchema(
    event_type=EventType.SIGN_UP,
    description="Fired when a new user signs up",
    required_fields=[],
    optional_fields=["method", "referral_code"],
    field_types={
        "method": "string",
        "referral_code": "string",
    },
    constraints={
        "method": {
            "enum": ["email", "google", "facebook", "apple", "sso"]
        },
    },
)

LOGIN_SCHEMA = EventSchema(
    event_type=EventType.LOGIN,
    description="Fired when a user logs in",
    required_fields=[],
    optional_fields=["method"],
    field_types={
        "method": "string",
    },
    constraints={
        "method": {
            "enum": ["email", "google", "facebook", "apple", "sso"]
        },
    },
)

CUSTOM_EVENT_SCHEMA = EventSchema(
    event_type=EventType.CUSTOM,
    description="Merchant-defined custom events",
    required_fields=["event_name"],
    optional_fields=[],  # Any properties allowed
    field_types={
        "event_name": "string",
    },
    constraints={
        "event_name": {"max_length": 100, "pattern": "^[a-z_][a-z0-9_]*$"},
    },
)


# =============================================================================
# Schema Registry
# =============================================================================

_SCHEMA_REGISTRY: dict[EventType, EventSchema] = {
    EventType.PAGE_VIEW: PAGE_VIEW_SCHEMA,
    EventType.PRODUCT_VIEW: PRODUCT_VIEW_SCHEMA,
    EventType.ADD_TO_CART: ADD_TO_CART_SCHEMA,
    EventType.REMOVE_FROM_CART: REMOVE_FROM_CART_SCHEMA,
    EventType.BEGIN_CHECKOUT: BEGIN_CHECKOUT_SCHEMA,
    EventType.PURCHASE: PURCHASE_SCHEMA,
    EventType.SEARCH: SEARCH_SCHEMA,
    EventType.SEARCH_CLICK: SEARCH_CLICK_SCHEMA,
    EventType.RECOMMENDATION_VIEW: RECOMMENDATION_VIEW_SCHEMA,
    EventType.RECOMMENDATION_CLICK: RECOMMENDATION_CLICK_SCHEMA,
    EventType.SIGN_UP: SIGN_UP_SCHEMA,
    EventType.LOGIN: LOGIN_SCHEMA,
    EventType.CUSTOM: CUSTOM_EVENT_SCHEMA,
}


def get_schema_for_event_type(event_type: EventType) -> Optional[EventSchema]:
    """
    Get the schema for an event type.
    
    Returns None if no schema is registered.
    """
    return _SCHEMA_REGISTRY.get(event_type)


def register_schema(schema: EventSchema) -> None:
    """
    Register a custom schema.
    
    Used by merchants to define custom event types.
    """
    _SCHEMA_REGISTRY[schema.event_type] = schema


def get_all_schemas() -> dict[EventType, EventSchema]:
    """Get all registered schemas."""
    return _SCHEMA_REGISTRY.copy()


def validate_schema(schema: EventSchema) -> list[str]:
    """
    Validate that a schema is well-formed.
    
    Returns list of validation errors, empty if valid.
    """
    errors = []
    
    if not schema.event_type:
        errors.append("event_type is required")
    
    if not schema.description:
        errors.append("description is required")
    
    # Check that required fields have types defined
    for field in schema.required_fields:
        if field not in schema.field_types:
            errors.append(f"Required field '{field}' missing from field_types")
    
    # Check that constraint fields exist
    for field in schema.constraints:
        if field not in schema.field_types and field not in schema.required_fields:
            errors.append(f"Constraint defined for unknown field '{field}'")
    
    return errors
