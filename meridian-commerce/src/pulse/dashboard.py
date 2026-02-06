"""
Pulse Dashboard Service

Serves dashboard data for the merchant portal.
Handles caching, access control, and data formatting.

Dashboard widgets:
- GMV summary card
- Real-time visitors
- Conversion funnel
- Revenue charts
- Top products
- Traffic sources
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from config.settings import settings
from src.core.cache import PulseCacheManager
from src.core.exceptions import MerchantNotFoundError
from src.pulse.aggregator import AggregationWindow, MetricsAggregator

logger = structlog.get_logger(__name__)


@dataclass
class DashboardConfig:
    """Configuration for a merchant's dashboard."""
    
    merchant_id: str
    widgets: list[str]
    refresh_interval: int = 60  # seconds
    default_window: AggregationWindow = AggregationWindow.DAILY
    timezone: str = "UTC"


class DashboardService:
    """
    Service for serving dashboard data to the merchant portal.
    
    Handles:
    - Data aggregation from multiple sources
    - Caching for fast response times
    - Access control per merchant
    - Widget configuration
    
    Usage:
        service = DashboardService()
        
        data = await service.get_dashboard(
            merchant_id="merch_123",
            window=AggregationWindow.DAILY,
        )
    """
    
    def __init__(self):
        self.aggregator = MetricsAggregator()
        self.cache = PulseCacheManager()
        
        # Default widget set
        self._default_widgets = [
            "summary",
            "realtime",
            "funnel",
            "revenue_chart",
            "top_products",
            "traffic_sources",
        ]
    
    async def get_dashboard(
        self,
        merchant_id: str,
        window: AggregationWindow = AggregationWindow.DAILY,
        widgets: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Get complete dashboard data for a merchant.
        
        Args:
            merchant_id: Merchant identifier
            window: Time window for metrics
            widgets: List of widgets to include (None = all)
        
        Returns:
            Dictionary with data for each widget
        """
        # Check cache first
        cached = await self.cache.get_dashboard_metrics(merchant_id)
        if cached:
            logger.debug("Dashboard cache hit", merchant_id=merchant_id)
            return cached
        
        widgets = widgets or self._default_widgets
        
        # Build dashboard data from multiple sources
        dashboard_data = {
            "merchant_id": merchant_id,
            "window": window.value,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "widgets": {},
        }
        
        # Fetch widget data in parallel
        tasks = {}
        
        if "summary" in widgets:
            tasks["summary"] = self._get_summary_widget(merchant_id, window)
        
        if "realtime" in widgets:
            tasks["realtime"] = self._get_realtime_widget(merchant_id)
        
        if "funnel" in widgets:
            tasks["funnel"] = self._get_funnel_widget(merchant_id, window)
        
        if "revenue_chart" in widgets:
            tasks["revenue_chart"] = self._get_revenue_chart_widget(merchant_id, window)
        
        if "top_products" in widgets:
            tasks["top_products"] = self._get_top_products_widget(merchant_id, window)
        
        if "traffic_sources" in widgets:
            tasks["traffic_sources"] = self._get_traffic_sources_widget(merchant_id, window)
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        for widget_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(
                    "Widget fetch failed",
                    widget=widget_name,
                    error=str(result),
                )
                dashboard_data["widgets"][widget_name] = {"error": str(result)}
            else:
                dashboard_data["widgets"][widget_name] = result
        
        # Cache the result
        await self.cache.cache_dashboard_metrics(merchant_id, dashboard_data)
        
        return dashboard_data
    
    async def _get_summary_widget(
        self,
        merchant_id: str,
        window: AggregationWindow,
    ) -> dict[str, Any]:
        """
        Get summary widget data.
        
        Shows key metrics with comparison to previous period:
        - GMV
        - Orders
        - Conversion Rate
        - Average Order Value
        """
        # Current period
        gmv = await self.aggregator.get_gmv(merchant_id, window)
        orders = await self.aggregator.get_order_count(merchant_id, window)
        cvr = await self.aggregator.get_conversion_rate(merchant_id, window)
        aov = await self.aggregator.get_average_order_value(merchant_id, window)
        
        # Previous period comparison would be calculated here
        # For now, simulate percentage changes
        
        return {
            "gmv": {
                "value": gmv.value,
                "change_percent": 12.5,
                "trend": "up",
            },
            "orders": {
                "value": orders.value,
                "change_percent": 8.2,
                "trend": "up",
            },
            "conversion_rate": {
                "value": cvr.value,
                "change_percent": -2.1,
                "trend": "down",
            },
            "aov": {
                "value": aov.value,
                "change_percent": 4.3,
                "trend": "up",
            },
        }
    
    async def _get_realtime_widget(
        self,
        merchant_id: str,
    ) -> dict[str, Any]:
        """
        Get real-time stats widget.
        
        Shows live metrics from the last 5 minutes.
        """
        stats = await self.aggregator.get_realtime_stats(merchant_id)
        
        return {
            "visitors_now": stats["visitors_now"],
            "gmv_last_5min": stats["gmv"],
            "orders_last_5min": stats["orders"],
            "timestamp": stats["timestamp"],
        }
    
    async def _get_funnel_widget(
        self,
        merchant_id: str,
        window: AggregationWindow,
    ) -> dict[str, Any]:
        """
        Get conversion funnel widget.
        
        Shows the e-commerce conversion funnel with counts
        and conversion rates between stages.
        """
        funnel = await self.aggregator.get_conversion_funnel(merchant_id, window)
        
        return {
            "stages": [stage.to_dict() for stage in funnel],
            "overall_conversion": funnel[-1].count / funnel[0].count * 100
                if funnel[0].count > 0 else 0,
        }
    
    async def _get_revenue_chart_widget(
        self,
        merchant_id: str,
        window: AggregationWindow,
    ) -> dict[str, Any]:
        """
        Get revenue time series chart.
        
        Shows GMV over time with configurable granularity.
        """
        # Determine granularity based on window
        if window == AggregationWindow.REALTIME:
            granularity = "minute"
            periods = 60
        elif window == AggregationWindow.HOURLY:
            granularity = "minute"
            periods = 60
        elif window == AggregationWindow.DAILY:
            granularity = "hour"
            periods = 24
        elif window == AggregationWindow.WEEKLY:
            granularity = "day"
            periods = 7
        else:
            granularity = "day"
            periods = 30
        
        timeseries = await self.aggregator.get_gmv_timeseries(
            merchant_id,
            window,
            granularity,
            periods,
        )
        
        return {
            "granularity": granularity,
            "data": timeseries,
        }
    
    async def _get_top_products_widget(
        self,
        merchant_id: str,
        window: AggregationWindow,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Get top products by revenue.
        
        Shows best-selling products with revenue and order count.
        """
        # In production, would query ClickHouse for top products
        # Aggregating purchase events by product_id
        
        # Simulated data
        products = [
            {
                "product_id": "prod_abc123",
                "name": "Premium Widget",
                "revenue": 4523.50,
                "orders": 45,
                "units": 67,
            },
            {
                "product_id": "prod_def456",
                "name": "Deluxe Gadget",
                "revenue": 3211.00,
                "orders": 32,
                "units": 32,
            },
            {
                "product_id": "prod_ghi789",
                "name": "Standard Thing",
                "revenue": 2890.25,
                "orders": 89,
                "units": 123,
            },
            {
                "product_id": "prod_jkl012",
                "name": "Basic Item",
                "revenue": 1567.00,
                "orders": 156,
                "units": 234,
            },
            {
                "product_id": "prod_mno345",
                "name": "Economy Option",
                "revenue": 890.50,
                "orders": 89,
                "units": 178,
            },
        ]
        
        return {
            "products": products[:limit],
        }
    
    async def _get_traffic_sources_widget(
        self,
        merchant_id: str,
        window: AggregationWindow,
    ) -> dict[str, Any]:
        """
        Get traffic sources breakdown.
        
        Shows where visitors and revenue come from.
        """
        breakdown = await self.aggregator.get_revenue_by_dimension(
            merchant_id,
            dimension="source",
            window=window,
        )
        
        return {
            "sources": breakdown,
        }
    
    # =========================================================================
    # Widget Configuration
    # =========================================================================
    
    async def get_widget_config(
        self,
        merchant_id: str,
    ) -> DashboardConfig:
        """
        Get dashboard configuration for a merchant.
        
        Merchants can customize which widgets appear and
        default settings.
        """
        # Would load from merchant settings
        # Placeholder with defaults
        
        return DashboardConfig(
            merchant_id=merchant_id,
            widgets=self._default_widgets,
            refresh_interval=60,
            default_window=AggregationWindow.DAILY,
            timezone="America/Los_Angeles",
        )
    
    async def update_widget_config(
        self,
        merchant_id: str,
        config: DashboardConfig,
    ) -> None:
        """Update dashboard configuration for a merchant."""
        # Would persist to database
        logger.info(
            "Dashboard config updated",
            merchant_id=merchant_id,
            widgets=config.widgets,
        )
    
    # =========================================================================
    # Cache Management
    # =========================================================================
    
    async def invalidate_cache(self, merchant_id: str) -> None:
        """
        Invalidate cached dashboard data for a merchant.
        
        Called when events are processed that would change metrics.
        """
        await self.cache.delete(f"dashboard:{merchant_id}")
        logger.debug("Dashboard cache invalidated", merchant_id=merchant_id)
    
    async def warm_cache(self, merchant_id: str) -> None:
        """
        Pre-populate cache for a merchant.
        
        Called during off-peak hours or after cache invalidation.
        """
        # Fetch dashboard to populate cache
        await self.get_dashboard(
            merchant_id,
            AggregationWindow.DAILY,
            self._default_widgets,
        )
        logger.debug("Dashboard cache warmed", merchant_id=merchant_id)


class DashboardExporter:
    """
    Exports dashboard data to various formats.
    
    Supports:
    - CSV export
    - PDF report generation
    - Scheduled email reports
    """
    
    def __init__(self, dashboard_service: DashboardService):
        self.dashboard = dashboard_service
    
    async def export_csv(
        self,
        merchant_id: str,
        window: AggregationWindow,
    ) -> str:
        """Export dashboard data as CSV."""
        data = await self.dashboard.get_dashboard(merchant_id, window)
        
        # Would generate CSV content
        # Placeholder
        return "timestamp,gmv,orders,conversion_rate\n..."
    
    async def generate_pdf_report(
        self,
        merchant_id: str,
        window: AggregationWindow,
    ) -> bytes:
        """Generate PDF report."""
        data = await self.dashboard.get_dashboard(merchant_id, window)
        
        # Would use a PDF generation library
        # Placeholder
        return b"PDF content"
    
    async def schedule_email_report(
        self,
        merchant_id: str,
        email: str,
        frequency: str,  # daily, weekly, monthly
    ) -> None:
        """Schedule recurring email reports."""
        # Would create a scheduled job
        logger.info(
            "Email report scheduled",
            merchant_id=merchant_id,
            email=email,
            frequency=frequency,
        )
