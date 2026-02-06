"""
Pulse Metrics Aggregator

Computes real-time metrics from Beacon events stored in ClickHouse.
Aggregations are cached in Redis for fast dashboard serving.

Key metrics:
- GMV (Gross Merchandise Value)
- Order count and value
- Conversion rates by funnel stage
- ARPU (Average Revenue Per User)
- Session and page view counts

Aggregation windows:
- Real-time (last 5 minutes)
- Hourly
- Daily
- Weekly
- Monthly
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import structlog

from config.settings import settings
from src.core.cache import cache, cached
from src.core.exceptions import AggregationError

logger = structlog.get_logger(__name__)


class AggregationWindow(str, Enum):
    """Time windows for metric aggregation."""
    REALTIME = "realtime"    # Last 5 minutes
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"
    
    @property
    def seconds(self) -> int:
        """Get window duration in seconds."""
        durations = {
            AggregationWindow.REALTIME: 300,
            AggregationWindow.HOURLY: 3600,
            AggregationWindow.DAILY: 86400,
            AggregationWindow.WEEKLY: 604800,
            AggregationWindow.MONTHLY: 2592000,
        }
        return durations.get(self, 86400)


@dataclass
class MetricResult:
    """Result of a metric aggregation."""
    
    metric_name: str
    value: Any
    window: AggregationWindow
    timestamp: datetime
    merchant_id: str
    dimensions: dict[str, str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "window": self.window.value,
            "timestamp": self.timestamp.isoformat(),
            "merchant_id": self.merchant_id,
            "dimensions": self.dimensions or {},
        }


@dataclass 
class FunnelStage:
    """Conversion funnel stage with counts."""
    
    name: str
    count: int
    conversion_rate: float  # Rate from previous stage
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "conversion_rate": self.conversion_rate,
        }


class MetricsAggregator:
    """
    Aggregates Beacon events into dashboard metrics.
    
    Queries ClickHouse for event aggregations and caches
    results in Redis for fast serving.
    
    Usage:
        aggregator = MetricsAggregator()
        
        gmv = await aggregator.get_gmv(
            merchant_id="merch_123",
            window=AggregationWindow.DAILY,
        )
        
        funnel = await aggregator.get_conversion_funnel(
            merchant_id="merch_123",
        )
    """
    
    def __init__(self):
        self._clickhouse_client = None  # Initialized lazily
        
    async def _get_clickhouse(self):
        """Get ClickHouse client (lazy initialization)."""
        if self._clickhouse_client is None:
            # In production, would use clickhouse-driver
            # Placeholder for now
            pass
        return self._clickhouse_client
    
    # =========================================================================
    # Revenue Metrics
    # =========================================================================
    
    @cached(ttl=60, key_prefix="pulse:gmv")
    async def get_gmv(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> MetricResult:
        """
        Get Gross Merchandise Value for a merchant.
        
        GMV = sum of all order subtotals (before tax/shipping)
        
        Args:
            merchant_id: Merchant to aggregate for
            window: Time window for aggregation
            start_time: Custom start time (for CUSTOM window)
            end_time: Custom end time (for CUSTOM window)
        
        Returns:
            MetricResult with GMV value
        """
        end_time = end_time or datetime.now(timezone.utc)
        start_time = start_time or (end_time - timedelta(seconds=window.seconds))
        
        # ClickHouse query for GMV
        # In production, this would execute against ClickHouse
        query = f"""
            SELECT
                sum(JSONExtractFloat(properties, 'revenue')) as gmv
            FROM events
            WHERE merchant_id = '{merchant_id}'
                AND event_type = 'purchase'
                AND received_at BETWEEN '{start_time.isoformat()}' 
                    AND '{end_time.isoformat()}'
        """
        
        try:
            # Simulated result - would come from ClickHouse
            gmv_value = Decimal("12345.67")
            
            logger.debug(
                "GMV calculated",
                merchant_id=merchant_id,
                window=window.value,
                gmv=float(gmv_value),
            )
            
            return MetricResult(
                metric_name="gmv",
                value=float(gmv_value),
                window=window,
                timestamp=end_time,
                merchant_id=merchant_id,
            )
            
        except Exception as e:
            logger.error(
                "GMV calculation failed",
                merchant_id=merchant_id,
                error=str(e),
            )
            raise AggregationError(f"Failed to calculate GMV: {e}", metric="gmv")
    
    @cached(ttl=60, key_prefix="pulse:orders")
    async def get_order_count(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> MetricResult:
        """Get order count for a merchant."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=window.seconds)
        
        # Simulated result
        order_count = 156
        
        return MetricResult(
            metric_name="order_count",
            value=order_count,
            window=window,
            timestamp=end_time,
            merchant_id=merchant_id,
        )
    
    @cached(ttl=60, key_prefix="pulse:aov")
    async def get_average_order_value(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> MetricResult:
        """
        Get Average Order Value (AOV) for a merchant.
        
        AOV = GMV / Order Count
        """
        gmv_result = await self.get_gmv(merchant_id, window)
        order_result = await self.get_order_count(merchant_id, window)
        
        if order_result.value == 0:
            aov = 0.0
        else:
            aov = gmv_result.value / order_result.value
        
        return MetricResult(
            metric_name="aov",
            value=round(aov, 2),
            window=window,
            timestamp=gmv_result.timestamp,
            merchant_id=merchant_id,
        )
    
    # =========================================================================
    # Traffic Metrics
    # =========================================================================
    
    @cached(ttl=30, key_prefix="pulse:sessions")
    async def get_session_count(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> MetricResult:
        """Get unique session count."""
        end_time = datetime.now(timezone.utc)
        
        # ClickHouse query for unique sessions
        # Would use uniqExact(session_id) in production
        session_count = 4523
        
        return MetricResult(
            metric_name="session_count",
            value=session_count,
            window=window,
            timestamp=end_time,
            merchant_id=merchant_id,
        )
    
    @cached(ttl=30, key_prefix="pulse:pageviews")
    async def get_page_views(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> MetricResult:
        """Get page view count."""
        end_time = datetime.now(timezone.utc)
        page_views = 18234
        
        return MetricResult(
            metric_name="page_views",
            value=page_views,
            window=window,
            timestamp=end_time,
            merchant_id=merchant_id,
        )
    
    # =========================================================================
    # Conversion Metrics
    # =========================================================================
    
    @cached(ttl=60, key_prefix="pulse:funnel")
    async def get_conversion_funnel(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> list[FunnelStage]:
        """
        Get conversion funnel metrics.
        
        Standard e-commerce funnel:
        1. Sessions (all visitors)
        2. Product Views (browsed products)
        3. Add to Cart (added items)
        4. Checkout Started (began checkout)
        5. Purchase (completed order)
        
        Returns list of FunnelStage with counts and conversion rates.
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=window.seconds)
        
        # In production, these would be ClickHouse aggregations
        # Each stage uses uniqExact on appropriate identifiers
        
        # Simulated funnel data
        stages_data = [
            ("Sessions", 4523),
            ("Product Views", 3211),
            ("Add to Cart", 856),
            ("Checkout Started", 412),
            ("Purchase", 156),
        ]
        
        stages = []
        prev_count = None
        
        for name, count in stages_data:
            if prev_count is None:
                conversion_rate = 100.0
            else:
                conversion_rate = (count / prev_count * 100) if prev_count > 0 else 0.0
            
            stages.append(FunnelStage(
                name=name,
                count=count,
                conversion_rate=round(conversion_rate, 2),
            ))
            prev_count = count
        
        logger.debug(
            "Funnel calculated",
            merchant_id=merchant_id,
            stages=[s.to_dict() for s in stages],
        )
        
        return stages
    
    @cached(ttl=60, key_prefix="pulse:cvr")
    async def get_conversion_rate(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> MetricResult:
        """
        Get overall conversion rate (purchases / sessions).
        
        This is the key metric for most merchants.
        """
        funnel = await self.get_conversion_funnel(merchant_id, window)
        
        sessions = funnel[0].count
        purchases = funnel[-1].count
        
        cvr = (purchases / sessions * 100) if sessions > 0 else 0.0
        
        return MetricResult(
            metric_name="conversion_rate",
            value=round(cvr, 2),
            window=window,
            timestamp=datetime.now(timezone.utc),
            merchant_id=merchant_id,
        )
    
    # =========================================================================
    # Customer Metrics
    # =========================================================================
    
    @cached(ttl=300, key_prefix="pulse:arpu")
    async def get_arpu(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.MONTHLY,
    ) -> MetricResult:
        """
        Get Average Revenue Per User (ARPU).
        
        ARPU = Total Revenue / Unique Customers
        
        Key metric for the Growth team.
        """
        # This would query both ClickHouse (revenue) and PostgreSQL (customer count)
        
        # Simulated result
        arpu_value = 87.34
        
        return MetricResult(
            metric_name="arpu",
            value=arpu_value,
            window=window,
            timestamp=datetime.now(timezone.utc),
            merchant_id=merchant_id,
        )
    
    @cached(ttl=300, key_prefix="pulse:new_customers")
    async def get_new_customer_count(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
    ) -> MetricResult:
        """Get count of new customers (first purchase)."""
        # Would compare customers who purchased in window
        # against historical customer list
        
        new_customers = 23
        
        return MetricResult(
            metric_name="new_customers",
            value=new_customers,
            window=window,
            timestamp=datetime.now(timezone.utc),
            merchant_id=merchant_id,
        )
    
    # =========================================================================
    # Real-time Metrics
    # =========================================================================
    
    async def get_realtime_stats(
        self,
        merchant_id: str,
    ) -> dict[str, Any]:
        """
        Get real-time statistics (last 5 minutes).
        
        Optimized for low latency - used by live dashboard widgets.
        """
        window = AggregationWindow.REALTIME
        
        # Parallel fetch of key metrics
        import asyncio
        
        gmv_task = self.get_gmv(merchant_id, window)
        orders_task = self.get_order_count(merchant_id, window)
        sessions_task = self.get_session_count(merchant_id, window)
        
        gmv, orders, sessions = await asyncio.gather(
            gmv_task, orders_task, sessions_task
        )
        
        return {
            "window": "realtime",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gmv": gmv.value,
            "orders": orders.value,
            "sessions": sessions.value,
            "visitors_now": 42,  # Active sessions in last minute
        }
    
    # =========================================================================
    # Time Series
    # =========================================================================
    
    @cached(ttl=300, key_prefix="pulse:timeseries")
    async def get_gmv_timeseries(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
        granularity: str = "hour",
        periods: int = 24,
    ) -> list[dict[str, Any]]:
        """
        Get GMV time series for charting.
        
        Args:
            merchant_id: Merchant ID
            window: Overall time window
            granularity: Data point frequency (hour, day, week)
            periods: Number of data points
        
        Returns:
            List of {timestamp, value} objects
        """
        # Would use ClickHouse time series aggregation
        # toStartOfHour, toStartOfDay, etc.
        
        # Simulated time series
        import random
        
        now = datetime.now(timezone.utc)
        data = []
        
        for i in range(periods):
            if granularity == "hour":
                ts = now - timedelta(hours=periods - i - 1)
            else:
                ts = now - timedelta(days=periods - i - 1)
            
            # Simulated value with some variation
            base_value = 1500 + random.uniform(-200, 200)
            
            data.append({
                "timestamp": ts.isoformat(),
                "value": round(base_value, 2),
            })
        
        return data
    
    # =========================================================================
    # Dimension Breakdown
    # =========================================================================
    
    @cached(ttl=300, key_prefix="pulse:breakdown")
    async def get_revenue_by_dimension(
        self,
        merchant_id: str,
        dimension: str,  # device, country, source, category
        window: AggregationWindow = AggregationWindow.DAILY,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get revenue breakdown by a dimension.
        
        Used for pie charts and tables showing revenue distribution.
        
        Args:
            merchant_id: Merchant ID
            dimension: Dimension to group by (device, country, source, category)
            window: Time window
            limit: Max number of segments
        
        Returns:
            List of {dimension_value, revenue, percentage} objects
        """
        # Simulated breakdown data
        if dimension == "device":
            breakdown = [
                {"value": "desktop", "revenue": 8500.0, "percentage": 55.2},
                {"value": "mobile", "revenue": 5200.0, "percentage": 33.8},
                {"value": "tablet", "revenue": 1700.0, "percentage": 11.0},
            ]
        elif dimension == "country":
            breakdown = [
                {"value": "US", "revenue": 10500.0, "percentage": 68.2},
                {"value": "CA", "revenue": 2100.0, "percentage": 13.6},
                {"value": "UK", "revenue": 1800.0, "percentage": 11.7},
                {"value": "Other", "revenue": 1000.0, "percentage": 6.5},
            ]
        elif dimension == "source":
            breakdown = [
                {"value": "direct", "revenue": 5500.0, "percentage": 35.7},
                {"value": "google", "revenue": 4200.0, "percentage": 27.3},
                {"value": "facebook", "revenue": 2800.0, "percentage": 18.2},
                {"value": "email", "revenue": 2000.0, "percentage": 13.0},
                {"value": "other", "revenue": 900.0, "percentage": 5.8},
            ]
        else:
            breakdown = []
        
        return breakdown[:limit]
