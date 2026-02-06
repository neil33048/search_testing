"""
Analytics API endpoints (Pulse).

Provides access to real-time and historical analytics:
- Dashboard metrics
- Conversion funnels
- GMV and revenue
- Traffic and engagement
"""

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from src.api.middleware.auth import get_current_merchant
from src.pulse.aggregator import AggregationWindow, MetricsAggregator
from src.pulse.dashboard import DashboardService

router = APIRouter()

# Service instances (would use DI in production)
aggregator = MetricsAggregator()
dashboard_service = DashboardService()


@router.get("/dashboard")
async def get_dashboard(
    window: str = Query("daily", description="Time window: realtime, hourly, daily, weekly, monthly"),
    widgets: Optional[str] = Query(None, description="Comma-separated widget names"),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get complete dashboard data.
    
    Returns all dashboard widgets for the specified time window.
    
    Available widgets:
    - summary: Key metrics (GMV, orders, CVR, AOV)
    - realtime: Live visitors and activity
    - funnel: Conversion funnel
    - revenue_chart: Revenue time series
    - top_products: Best selling products
    - traffic_sources: Traffic breakdown
    """
    # Parse window
    window_map = {
        "realtime": AggregationWindow.REALTIME,
        "hourly": AggregationWindow.HOURLY,
        "daily": AggregationWindow.DAILY,
        "weekly": AggregationWindow.WEEKLY,
        "monthly": AggregationWindow.MONTHLY,
    }
    agg_window = window_map.get(window, AggregationWindow.DAILY)
    
    # Parse widgets
    widget_list = None
    if widgets:
        widget_list = [w.strip() for w in widgets.split(",")]
    
    return await dashboard_service.get_dashboard(
        merchant_id=merchant_id,
        window=agg_window,
        widgets=widget_list,
    )


@router.get("/gmv")
async def get_gmv(
    window: str = Query("daily", description="Time window"),
    start_date: Optional[date] = Query(None, description="Start date for custom window"),
    end_date: Optional[date] = Query(None, description="End date for custom window"),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get GMV (Gross Merchandise Value) for the merchant.
    
    GMV = sum of order subtotals (excludes tax and shipping).
    This is the primary metric for merchant tier calculations.
    """
    window_map = {
        "realtime": AggregationWindow.REALTIME,
        "hourly": AggregationWindow.HOURLY,
        "daily": AggregationWindow.DAILY,
        "weekly": AggregationWindow.WEEKLY,
        "monthly": AggregationWindow.MONTHLY,
    }
    
    agg_window = window_map.get(window, AggregationWindow.DAILY)
    
    # Convert dates to datetime if provided
    start_time = datetime.combine(start_date, datetime.min.time()) if start_date else None
    end_time = datetime.combine(end_date, datetime.max.time()) if end_date else None
    
    result = await aggregator.get_gmv(
        merchant_id=merchant_id,
        window=agg_window,
        start_time=start_time,
        end_time=end_time,
    )
    
    return result.to_dict()


@router.get("/funnel")
async def get_conversion_funnel(
    window: str = Query("daily", description="Time window"),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get conversion funnel metrics.
    
    Standard e-commerce funnel stages:
    1. Sessions
    2. Product Views
    3. Add to Cart
    4. Checkout Started
    5. Purchase
    
    Returns counts and conversion rates between stages.
    """
    window_map = {
        "daily": AggregationWindow.DAILY,
        "weekly": AggregationWindow.WEEKLY,
        "monthly": AggregationWindow.MONTHLY,
    }
    agg_window = window_map.get(window, AggregationWindow.DAILY)
    
    funnel = await aggregator.get_conversion_funnel(
        merchant_id=merchant_id,
        window=agg_window,
    )
    
    return {
        "window": window,
        "stages": [stage.to_dict() for stage in funnel],
        "overall_conversion_rate": (
            funnel[-1].count / funnel[0].count * 100
            if funnel and funnel[0].count > 0
            else 0
        ),
    }


@router.get("/realtime")
async def get_realtime_stats(
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get real-time statistics (last 5 minutes).
    
    Returns:
    - Current visitors
    - Recent GMV
    - Recent orders
    - Active sessions
    """
    return await aggregator.get_realtime_stats(merchant_id)


@router.get("/revenue/breakdown")
async def get_revenue_breakdown(
    dimension: str = Query("source", description="Dimension: source, device, country, category"),
    window: str = Query("daily", description="Time window"),
    limit: int = Query(10, description="Max segments", ge=1, le=50),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get revenue breakdown by dimension.
    
    Available dimensions:
    - source: Traffic source (Google, Facebook, Direct, etc.)
    - device: Device type (Desktop, Mobile, Tablet)
    - country: Customer country
    - category: Product category
    """
    window_map = {
        "daily": AggregationWindow.DAILY,
        "weekly": AggregationWindow.WEEKLY,
        "monthly": AggregationWindow.MONTHLY,
    }
    agg_window = window_map.get(window, AggregationWindow.DAILY)
    
    breakdown = await aggregator.get_revenue_by_dimension(
        merchant_id=merchant_id,
        dimension=dimension,
        window=agg_window,
        limit=limit,
    )
    
    return {
        "dimension": dimension,
        "window": window,
        "segments": breakdown,
    }


@router.get("/metrics/{metric_name}")
async def get_metric(
    metric_name: str,
    window: str = Query("daily"),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get a specific metric.
    
    Available metrics:
    - gmv: Gross Merchandise Value
    - orders: Order count
    - aov: Average Order Value
    - cvr: Conversion Rate
    - sessions: Session count
    - arpu: Average Revenue Per User
    """
    window_map = {
        "daily": AggregationWindow.DAILY,
        "weekly": AggregationWindow.WEEKLY,
        "monthly": AggregationWindow.MONTHLY,
    }
    agg_window = window_map.get(window, AggregationWindow.DAILY)
    
    metric_methods = {
        "gmv": aggregator.get_gmv,
        "orders": aggregator.get_order_count,
        "aov": aggregator.get_average_order_value,
        "cvr": aggregator.get_conversion_rate,
        "sessions": aggregator.get_session_count,
        "arpu": aggregator.get_arpu,
    }
    
    if metric_name not in metric_methods:
        return {"error": f"Unknown metric: {metric_name}"}
    
    result = await metric_methods[metric_name](merchant_id, agg_window)
    return result.to_dict()
