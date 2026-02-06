"""
Pulse - Real-Time Analytics Engine

Pulse powers the Meridian Commerce merchant dashboard with
live metrics, aggregations, and alerts.

Key capabilities:
- Real-time GMV and order tracking
- Conversion funnel analysis
- Customer cohort metrics
- Anomaly detection and alerting

Data sources:
- ClickHouse for real-time event aggregation
- PostgreSQL for dimension lookups
- Redis for caching dashboard data

Architecture:
- Aggregator: Computes metrics from raw events
- Dashboard: Serves dashboard API and caching
- Alerts: Monitors metrics and triggers notifications
"""

from src.pulse.aggregator import MetricsAggregator, AggregationWindow
from src.pulse.dashboard import DashboardService
from src.pulse.alerts import AlertManager, AlertRule

__all__ = [
    "MetricsAggregator",
    "AggregationWindow",
    "DashboardService", 
    "AlertManager",
    "AlertRule",
]
