"""
Beacon - Event Collection System

Beacon is Meridian's real-time event ingestion system that collects
behavioral data from merchant storefronts. It handles 50M+ events/day
with low latency and high reliability.

Architecture:
1. Events come in via HTTP API or JavaScript SDK
2. Validated against schemas
3. Batched and sent to Kinesis
4. Processed by Forge into data warehouse

Key components:
- collector.py: Event ingestion endpoint
- validators.py: Schema validation
- schemas.py: Event type definitions
- batcher.py: Kinesis batching logic
"""

from src.beacon.collector import EventCollector
from src.beacon.validators import EventValidator
from src.beacon.schemas import EventSchema, get_schema_for_event_type

__all__ = [
    "EventCollector",
    "EventValidator", 
    "EventSchema",
    "get_schema_for_event_type",
]
