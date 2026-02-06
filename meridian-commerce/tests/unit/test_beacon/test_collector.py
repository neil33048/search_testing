"""
Unit tests for Beacon Event Collector.
"""

import pytest
from datetime import datetime, timezone

from src.beacon.collector import EventCollector, EnrichedEvent, BatchBuffer
from src.beacon.schemas import EventSchema
from src.core.exceptions import EventValidationError, RateLimitError
from src.models.event import EventType


class TestBatchBuffer:
    """Tests for BatchBuffer class."""
    
    def test_buffer_add_event(self):
        """Test adding events to buffer."""
        buffer = BatchBuffer()
        
        event = EnrichedEvent(
            id="evt_123",
            merchant_id="merch_test",
            event_type=EventType.PAGE_VIEW,
            properties={},
            context={},
            timestamp=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            session_id="sess_123",
            anonymous_id="anon_123",
        )
        
        buffer.add(event)
        
        assert buffer.size == 1
    
    def test_buffer_drain(self):
        """Test draining events from buffer."""
        buffer = BatchBuffer()
        
        # Add events
        for i in range(5):
            event = EnrichedEvent(
                id=f"evt_{i}",
                merchant_id="merch_test",
                event_type=EventType.PAGE_VIEW,
                properties={},
                context={},
                timestamp=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                session_id="sess_123",
                anonymous_id="anon_123",
            )
            buffer.add(event)
        
        assert buffer.size == 5
        
        # Drain
        events = buffer.drain()
        
        assert len(events) == 5
        assert buffer.size == 0


class TestEventCollector:
    """Tests for EventCollector class."""
    
    @pytest.fixture
    def collector(self):
        """Create collector instance."""
        return EventCollector()
    
    @pytest.mark.asyncio
    async def test_collect_valid_event(self, collector):
        """Test collecting a valid event."""
        raw_event = {
            "merchant_id": "merch_123",
            "event_type": "page_view",
            "properties": {"page_path": "/home"},
            "context": {},
            "session_id": "sess_abc",
            "anonymous_id": "anon_xyz",
        }
        
        result = await collector.collect(raw_event)
        
        assert result.id.startswith("evt_")
        assert result.merchant_id == "merch_123"
        assert result.event_type == EventType.PAGE_VIEW
    
    @pytest.mark.asyncio
    async def test_collect_missing_merchant_id(self, collector):
        """Test that missing merchant_id raises error."""
        raw_event = {
            "event_type": "page_view",
            "properties": {},
        }
        
        with pytest.raises(EventValidationError) as exc_info:
            await collector.collect(raw_event)
        
        assert "merchant_id" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_collect_batch(self, collector):
        """Test collecting a batch of events."""
        events = [
            {
                "merchant_id": "merch_123",
                "event_type": "page_view",
                "properties": {"page_path": f"/page/{i}"},
            }
            for i in range(5)
        ]
        
        results = await collector.collect_batch(events)
        
        assert len(results) == 5
    
    def test_collector_metrics(self, collector):
        """Test that metrics are tracked."""
        metrics = collector.get_metrics()
        
        assert "events_received" in metrics
        assert "events_validated" in metrics
        assert "batches_sent" in metrics


class TestEnrichedEvent:
    """Tests for EnrichedEvent dataclass."""
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        event = EnrichedEvent(
            id="evt_test123",
            merchant_id="merch_abc",
            event_type=EventType.PRODUCT_VIEW,
            properties={"product_id": "prod_xyz"},
            context={"device": "mobile"},
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            received_at=datetime(2024, 1, 15, 12, 0, 1, tzinfo=timezone.utc),
            session_id="sess_123",
            anonymous_id="anon_456",
            user_id="user_789",
        )
        
        result = event.to_dict()
        
        assert result["id"] == "evt_test123"
        assert result["merchant_id"] == "merch_abc"
        assert result["event_type"] == "product_view"
        assert result["properties"]["product_id"] == "prod_xyz"
        assert result["user_id"] == "user_789"
