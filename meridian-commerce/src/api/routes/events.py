"""
Events API endpoints (Beacon).

Handles event ingestion from merchant storefronts.
Events are validated, enriched, and sent to Kinesis for processing.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.api.middleware.auth import get_current_merchant
from src.beacon.collector import EventCollector

router = APIRouter()

# Collector instance (would use DI in production)
collector = EventCollector()


class EventPayload(BaseModel):
    """Single event payload."""
    
    event_type: str = Field(..., description="Event type (e.g., product_view, purchase)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Event properties")
    context: dict[str, Any] = Field(default_factory=dict, description="Event context")
    timestamp: str | None = Field(None, description="Event timestamp (ISO 8601)")
    session_id: str | None = Field(None, description="Session ID")
    anonymous_id: str | None = Field(None, description="Anonymous visitor ID")
    user_id: str | None = Field(None, description="Logged-in user ID")


class BatchEventPayload(BaseModel):
    """Batch of events."""
    
    events: list[EventPayload] = Field(..., description="List of events")


@router.post("/track")
async def track_event(
    event: EventPayload,
    request: Request,
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Track a single event.
    
    Events are validated against their schema and enriched with:
    - Geo data (from IP)
    - Device info (from User-Agent)
    - Server timestamp
    
    Common event types:
    - page_view: User views a page
    - product_view: User views a product
    - add_to_cart: User adds item to cart
    - purchase: Order completed
    - search: User searches
    
    See /docs for full event schema documentation.
    """
    # Get client info for enrichment
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    # Build raw event
    raw_event = {
        "merchant_id": merchant_id,
        "event_type": event.event_type,
        "properties": event.properties,
        "context": event.context,
        "timestamp": event.timestamp,
        "session_id": event.session_id,
        "anonymous_id": event.anonymous_id,
        "user_id": event.user_id,
    }
    
    # Collect event
    enriched = await collector.collect(
        raw_event,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    return {
        "success": True,
        "event_id": enriched.id,
    }


@router.post("/batch")
async def track_batch(
    batch: BatchEventPayload,
    request: Request,
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Track multiple events in a batch.
    
    More efficient than individual calls for high-volume tracking.
    Failed events are logged but don't fail the entire batch.
    
    Maximum batch size: 100 events
    """
    if len(batch.events) > 100:
        return {
            "success": False,
            "error": "Batch size exceeds maximum of 100 events",
        }
    
    # Get client info
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    
    # Build raw events
    raw_events = []
    for event in batch.events:
        raw_events.append({
            "merchant_id": merchant_id,
            "event_type": event.event_type,
            "properties": event.properties,
            "context": event.context,
            "timestamp": event.timestamp,
            "session_id": event.session_id,
            "anonymous_id": event.anonymous_id,
            "user_id": event.user_id,
        })
    
    # Collect batch
    results = await collector.collect_batch(
        raw_events,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    return {
        "success": True,
        "accepted": len(results),
        "total": len(batch.events),
        "event_ids": [e.id for e in results],
    }


@router.get("/types")
async def list_event_types() -> dict[str, Any]:
    """
    List supported event types and their schemas.
    
    Returns documentation for each event type including
    required and optional properties.
    """
    from src.beacon.schemas import get_all_schemas
    
    schemas = get_all_schemas()
    
    event_types = {}
    for event_type, schema in schemas.items():
        event_types[event_type.value] = {
            "description": schema.description,
            "required_fields": schema.required_fields,
            "optional_fields": schema.optional_fields,
            "field_types": schema.field_types,
        }
    
    return {"event_types": event_types}


@router.get("/metrics")
async def get_beacon_metrics(
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get Beacon ingestion metrics.
    
    Returns statistics about event collection:
    - Events received
    - Validation pass/fail rates
    - Batches sent to Kinesis
    """
    return collector.get_metrics()
