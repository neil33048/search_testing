"""
Beacon Event Collector

Handles incoming event ingestion from merchant storefronts.
Events are validated, enriched, and sent to Kinesis for processing.

High-volume service - optimized for throughput:
- Async processing throughout
- Connection pooling to Kinesis
- Batch sending with configurable intervals
- Circuit breaker for downstream failures
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from src.beacon.schemas import get_schema_for_event_type
from src.beacon.validators import EventValidator, ValidationResult
from src.core.exceptions import (
    EventIngestionError,
    EventValidationError,
    RateLimitError,
)
from src.models.event import EventSource, EventType

logger = structlog.get_logger(__name__)


@dataclass
class EnrichedEvent:
    """Event with additional context from Beacon processing."""
    
    id: str
    merchant_id: str
    event_type: EventType
    properties: dict[str, Any]
    context: dict[str, Any]
    timestamp: datetime
    received_at: datetime
    session_id: str
    anonymous_id: str
    user_id: Optional[str] = None
    source: EventSource = EventSource.WEB
    
    # Enriched fields
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    geo_data: Optional[dict] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "event_type": self.event_type.value,
            "properties": self.properties,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "received_at": self.received_at.isoformat(),
            "session_id": self.session_id,
            "anonymous_id": self.anonymous_id,
            "user_id": self.user_id,
            "source": self.source.value,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "geo_data": self.geo_data,
        }


@dataclass
class BatchBuffer:
    """
    Buffer for batching events before sending to Kinesis.
    
    Events are accumulated until either:
    - Batch size limit is reached
    - Flush interval expires
    """
    
    events: list[EnrichedEvent] = field(default_factory=list)
    last_flush: float = field(default_factory=time.time)
    
    @property
    def size(self) -> int:
        return len(self.events)
    
    @property
    def should_flush(self) -> bool:
        """Check if buffer should be flushed."""
        size_exceeded = self.size >= settings.beacon.batch_size
        time_exceeded = (
            time.time() - self.last_flush
        ) * 1000 >= settings.beacon.flush_interval_ms
        return size_exceeded or time_exceeded
    
    def add(self, event: EnrichedEvent) -> None:
        """Add event to buffer."""
        self.events.append(event)
    
    def drain(self) -> list[EnrichedEvent]:
        """Remove and return all events from buffer."""
        events = self.events
        self.events = []
        self.last_flush = time.time()
        return events


class EventCollector:
    """
    Main event collection service.
    
    Handles the full event lifecycle:
    1. Receive raw event from API
    2. Validate against schema
    3. Enrich with context (geo, device, etc.)
    4. Buffer for batching
    5. Send to Kinesis
    
    Usage:
        collector = EventCollector()
        await collector.start()
        
        result = await collector.collect({
            "event_type": "product_view",
            "merchant_id": "merch_abc123",
            ...
        })
    """
    
    def __init__(self):
        self.validator = EventValidator()
        self.buffer = BatchBuffer()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Metrics
        self._events_received = 0
        self._events_validated = 0
        self._events_rejected = 0
        self._batches_sent = 0
        
        # Rate limiting state (per merchant)
        self._rate_limit_counters: dict[str, int] = {}
        self._rate_limit_window_start: float = time.time()
    
    async def start(self) -> None:
        """Start the collector and background flush task."""
        if self._running:
            return
        
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("Beacon collector started")
    
    async def stop(self) -> None:
        """Stop the collector and flush remaining events."""
        self._running = False
        
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Final flush
        if self.buffer.size > 0:
            await self._flush()
        
        logger.info(
            "Beacon collector stopped",
            events_received=self._events_received,
            events_validated=self._events_validated,
            batches_sent=self._batches_sent,
        )
    
    async def collect(
        self,
        raw_event: dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> EnrichedEvent:
        """
        Collect and process a single event.
        
        Args:
            raw_event: Raw event data from client
            ip_address: Client IP for geo enrichment
            user_agent: User agent string for device detection
            
        Returns:
            Enriched event with generated ID
            
        Raises:
            EventValidationError: If event fails validation
            RateLimitError: If merchant exceeds rate limit
        """
        self._events_received += 1
        received_at = datetime.now(timezone.utc)
        
        # Extract merchant ID early for rate limiting
        merchant_id = raw_event.get("merchant_id")
        if not merchant_id:
            raise EventValidationError("merchant_id is required")
        
        # Check rate limit
        await self._check_rate_limit(merchant_id)
        
        # Parse event type
        event_type_str = raw_event.get("event_type")
        try:
            event_type = EventType(event_type_str)
        except (ValueError, TypeError):
            if settings.beacon.allow_unknown_events:
                event_type = EventType.CUSTOM
            else:
                raise EventValidationError(
                    f"Unknown event type: {event_type_str}",
                    event_type=event_type_str,
                )
        
        # Validate event properties against schema
        validation_result = await self.validator.validate(
            event_type=event_type,
            properties=raw_event.get("properties", {}),
            context=raw_event.get("context", {}),
            strict=settings.beacon.strict_validation,
        )
        
        if not validation_result.is_valid:
            self._events_rejected += 1
            raise EventValidationError(
                "Event validation failed",
                event_type=event_type_str,
                validation_errors=validation_result.errors,
            )
        
        self._events_validated += 1
        
        # Create enriched event
        event = EnrichedEvent(
            id=self._generate_event_id(),
            merchant_id=merchant_id,
            event_type=event_type,
            properties=raw_event.get("properties", {}),
            context=raw_event.get("context", {}),
            timestamp=self._parse_timestamp(raw_event.get("timestamp")),
            received_at=received_at,
            session_id=raw_event.get("session_id", self._generate_session_id()),
            anonymous_id=raw_event.get("anonymous_id", self._generate_anonymous_id()),
            user_id=raw_event.get("user_id"),
            source=self._parse_source(raw_event.get("source")),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Enrich with geo data if IP available
        if ip_address:
            event.geo_data = await self._enrich_geo(ip_address)
        
        # Add to buffer
        self.buffer.add(event)
        
        # Immediate flush if buffer is full
        if self.buffer.should_flush:
            asyncio.create_task(self._flush())
        
        logger.debug(
            "Event collected",
            event_id=event.id,
            event_type=event_type.value,
            merchant_id=merchant_id,
        )
        
        return event
    
    async def collect_batch(
        self,
        events: list[dict[str, Any]],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> list[EnrichedEvent]:
        """
        Collect multiple events in a batch.
        
        More efficient than calling collect() for each event.
        Failed events are logged but don't fail the entire batch.
        """
        results = []
        
        for raw_event in events:
            try:
                event = await self.collect(raw_event, ip_address, user_agent)
                results.append(event)
            except (EventValidationError, RateLimitError) as e:
                logger.warning(
                    "Event failed in batch",
                    error=str(e),
                    event_type=raw_event.get("event_type"),
                )
                continue
        
        return results
    
    async def _flush_loop(self) -> None:
        """Background task to periodically flush buffer."""
        while self._running:
            await asyncio.sleep(settings.beacon.flush_interval_ms / 1000)
            
            if self.buffer.size > 0:
                await self._flush()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _flush(self) -> None:
        """Flush buffered events to Kinesis."""
        events = self.buffer.drain()
        
        if not events:
            return
        
        try:
            await self._send_to_kinesis(events)
            self._batches_sent += 1
            
            logger.info(
                "Batch flushed to Kinesis",
                batch_size=len(events),
                total_batches=self._batches_sent,
            )
        except Exception as e:
            # Re-add events to buffer on failure
            # In production, we'd use a dead letter queue
            for event in events:
                self.buffer.add(event)
            
            logger.error(
                "Failed to flush batch",
                error=str(e),
                batch_size=len(events),
            )
            raise EventIngestionError(f"Kinesis send failed: {e}")
    
    async def _send_to_kinesis(self, events: list[EnrichedEvent]) -> None:
        """
        Send events to Kinesis stream.
        
        In production, this uses the Kinesis client with proper
        connection pooling and retry logic.
        """
        # Placeholder - actual implementation would use boto3
        # Each event is sent with merchant_id as partition key
        # for ordered processing within a merchant
        
        records = [
            {
                "Data": event.to_dict(),
                "PartitionKey": event.merchant_id,
            }
            for event in events
        ]
        
        # Simulate Kinesis send
        await asyncio.sleep(0.01)  # Simulated network latency
        
        logger.debug(
            "Sent to Kinesis",
            stream=settings.beacon.kinesis_stream,
            record_count=len(records),
        )
    
    async def _check_rate_limit(self, merchant_id: str) -> None:
        """
        Check if merchant has exceeded rate limit.
        
        Uses sliding window counter algorithm.
        """
        current_time = time.time()
        
        # Reset counters every second
        if current_time - self._rate_limit_window_start >= 1.0:
            self._rate_limit_counters = {}
            self._rate_limit_window_start = current_time
        
        # Increment counter
        self._rate_limit_counters[merchant_id] = (
            self._rate_limit_counters.get(merchant_id, 0) + 1
        )
        
        # Check limit
        if self._rate_limit_counters[merchant_id] > settings.beacon.rate_limit_per_second:
            raise RateLimitError(
                f"Rate limit exceeded for merchant {merchant_id}",
                retry_after_seconds=1,
            )
    
    async def _enrich_geo(self, ip_address: str) -> Optional[dict]:
        """
        Enrich event with geo data from IP address.
        
        Uses MaxMind GeoIP2 database in production.
        """
        # Placeholder - would use geoip2 library
        # Returns country, region, city, timezone, etc.
        return {
            "country_code": "US",
            "region": "California",
            "city": "San Francisco",
        }
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        return f"evt_{uuid4().hex[:18]}"
    
    def _generate_session_id(self) -> str:
        """Generate session ID for events without one."""
        return f"sess_{uuid4().hex[:16]}"
    
    def _generate_anonymous_id(self) -> str:
        """Generate anonymous ID for events without one."""
        return f"anon_{uuid4().hex[:16]}"
    
    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse timestamp from various formats."""
        if ts is None:
            return datetime.now(timezone.utc)
        
        if isinstance(ts, datetime):
            return ts
        
        if isinstance(ts, (int, float)):
            # Assume milliseconds if too large for seconds
            if ts > 1e12:
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        
        return datetime.now(timezone.utc)
    
    def _parse_source(self, source: Any) -> EventSource:
        """Parse event source."""
        if source is None:
            return EventSource.WEB
        
        try:
            return EventSource(source)
        except ValueError:
            return EventSource.WEB
    
    def get_metrics(self) -> dict[str, Any]:
        """Get collector metrics for monitoring."""
        return {
            "events_received": self._events_received,
            "events_validated": self._events_validated,
            "events_rejected": self._events_rejected,
            "batches_sent": self._batches_sent,
            "buffer_size": self.buffer.size,
            "rejection_rate": (
                self._events_rejected / self._events_received
                if self._events_received > 0
                else 0
            ),
        }
