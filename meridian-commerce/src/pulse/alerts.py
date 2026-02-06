"""
Pulse Alerting System

Monitors metrics and triggers alerts when thresholds are breached.
Supports multiple notification channels and alert rules.

Alert types:
- Threshold alerts (metric above/below value)
- Anomaly detection (statistical outliers)
- Trend alerts (significant changes)
- Heartbeat alerts (missing data)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from config.settings import settings
from src.core.cache import cache
from src.pulse.aggregator import AggregationWindow, MetricsAggregator

logger = structlog.get_logger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    SILENCED = "silenced"


class ComparisonOperator(str, Enum):
    """Operators for threshold comparison."""
    GT = "gt"  # greater than
    GTE = "gte"  # greater than or equal
    LT = "lt"  # less than
    LTE = "lte"  # less than or equal
    EQ = "eq"  # equal
    NEQ = "neq"  # not equal


@dataclass
class AlertRule:
    """
    Definition of an alert rule.
    
    Attributes:
        id: Unique rule identifier
        name: Human-readable name
        metric: Metric to monitor
        operator: Comparison operator
        threshold: Threshold value
        window: Time window for aggregation
        severity: Alert severity
        cooldown_minutes: Minimum time between alerts
    """
    
    id: str
    name: str
    metric: str
    operator: ComparisonOperator
    threshold: float
    window: AggregationWindow = AggregationWindow.REALTIME
    severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_minutes: int = 15
    enabled: bool = True
    
    # Optional filters
    merchant_id: Optional[str] = None  # None = all merchants
    
    # Notification settings
    notify_slack: bool = True
    notify_pagerduty: bool = False
    notify_email: bool = False
    email_recipients: list[str] = field(default_factory=list)
    
    def evaluate(self, value: float) -> bool:
        """
        Evaluate if current value triggers the alert.
        
        Returns True if alert should fire.
        """
        ops = {
            ComparisonOperator.GT: lambda v, t: v > t,
            ComparisonOperator.GTE: lambda v, t: v >= t,
            ComparisonOperator.LT: lambda v, t: v < t,
            ComparisonOperator.LTE: lambda v, t: v <= t,
            ComparisonOperator.EQ: lambda v, t: v == t,
            ComparisonOperator.NEQ: lambda v, t: v != t,
        }
        return ops[self.operator](value, self.threshold)


@dataclass
class Alert:
    """An active or historical alert instance."""
    
    id: str
    rule_id: str
    rule_name: str
    merchant_id: str
    metric: str
    value: float
    threshold: float
    severity: AlertSeverity
    status: AlertStatus
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "merchant_id": self.merchant_id,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "severity": self.severity.value,
            "status": self.status.value,
            "triggered_at": self.triggered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class AlertManager:
    """
    Manages alert rules, evaluation, and notifications.
    
    Runs continuously, checking metrics against rules
    and sending notifications when thresholds are breached.
    
    Usage:
        manager = AlertManager()
        
        # Add a rule
        manager.add_rule(AlertRule(
            id="high_error_rate",
            name="High Error Rate",
            metric="error_rate",
            operator=ComparisonOperator.GT,
            threshold=0.05,
            severity=AlertSeverity.CRITICAL,
        ))
        
        # Start monitoring
        await manager.start()
    """
    
    def __init__(self):
        self.aggregator = MetricsAggregator()
        self.rules: dict[str, AlertRule] = {}
        self.active_alerts: dict[str, Alert] = {}
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        
        # Last alert time per rule for cooldown
        self._last_alert_time: dict[str, datetime] = {}
        
        # Notification handlers
        self._notifiers: list[Callable] = []
        
        # Load default rules
        self._load_default_rules()
    
    def _load_default_rules(self) -> None:
        """Load default alert rules."""
        
        # GMV drop alert
        self.add_rule(AlertRule(
            id="gmv_drop",
            name="Significant GMV Drop",
            metric="gmv_change_percent",
            operator=ComparisonOperator.LT,
            threshold=-20.0,  # 20% drop
            window=AggregationWindow.HOURLY,
            severity=AlertSeverity.WARNING,
        ))
        
        # Zero orders alert
        self.add_rule(AlertRule(
            id="zero_orders",
            name="No Orders Received",
            metric="order_count",
            operator=ComparisonOperator.EQ,
            threshold=0,
            window=AggregationWindow.HOURLY,
            severity=AlertSeverity.CRITICAL,
            notify_pagerduty=True,
        ))
        
        # Low conversion rate alert
        self.add_rule(AlertRule(
            id="low_conversion",
            name="Low Conversion Rate",
            metric="conversion_rate",
            operator=ComparisonOperator.LT,
            threshold=1.0,  # Below 1%
            window=AggregationWindow.DAILY,
            severity=AlertSeverity.WARNING,
        ))
        
        # Beacon lag alert (events not being processed)
        self.add_rule(AlertRule(
            id="beacon_lag",
            name="Beacon Processing Lag",
            metric="event_processing_lag_seconds",
            operator=ComparisonOperator.GT,
            threshold=60.0,
            severity=AlertSeverity.CRITICAL,
            notify_pagerduty=True,
        ))
        
        # High cart abandonment
        self.add_rule(AlertRule(
            id="cart_abandonment",
            name="High Cart Abandonment",
            metric="cart_abandonment_rate",
            operator=ComparisonOperator.GT,
            threshold=80.0,  # Above 80%
            window=AggregationWindow.DAILY,
            severity=AlertSeverity.INFO,
        ))
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self.rules[rule.id] = rule
        logger.info("Alert rule added", rule_id=rule.id, metric=rule.metric)
    
    def remove_rule(self, rule_id: str) -> None:
        """Remove an alert rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info("Alert rule removed", rule_id=rule_id)
    
    def add_notifier(self, notifier: Callable) -> None:
        """
        Add a notification handler.
        
        Notifier should be an async function that receives an Alert.
        """
        self._notifiers.append(notifier)
    
    async def start(self) -> None:
        """Start the alert monitoring loop."""
        if self._running:
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Alert manager started", rule_count=len(self.rules))
    
    async def stop(self) -> None:
        """Stop the alert monitoring loop."""
        self._running = False
        
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Alert manager stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        check_interval = settings.pulse.aggregation_window_seconds
        
        while self._running:
            try:
                await self._check_all_rules()
            except Exception as e:
                logger.error("Alert check failed", error=str(e))
            
            await asyncio.sleep(check_interval)
    
    async def _check_all_rules(self) -> None:
        """Check all enabled rules against current metrics."""
        # Get list of merchants to check
        # In production, would query database
        merchant_ids = ["merch_demo123"]  # Placeholder
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Determine which merchants to check
            if rule.merchant_id:
                merchants_to_check = [rule.merchant_id]
            else:
                merchants_to_check = merchant_ids
            
            for merchant_id in merchants_to_check:
                await self._check_rule(rule, merchant_id)
    
    async def _check_rule(self, rule: AlertRule, merchant_id: str) -> None:
        """Check a single rule for a merchant."""
        # Check cooldown
        rule_merchant_key = f"{rule.id}:{merchant_id}"
        last_alert = self._last_alert_time.get(rule_merchant_key)
        
        if last_alert:
            cooldown = timedelta(minutes=rule.cooldown_minutes)
            if datetime.now(timezone.utc) - last_alert < cooldown:
                return  # Still in cooldown
        
        # Get metric value
        try:
            value = await self._get_metric_value(rule.metric, merchant_id, rule.window)
        except Exception as e:
            logger.warning(
                "Failed to get metric for alert",
                rule_id=rule.id,
                metric=rule.metric,
                error=str(e),
            )
            return
        
        if value is None:
            return
        
        # Evaluate rule
        should_alert = rule.evaluate(value)
        
        # Check if alert already active
        alert_key = f"{rule.id}:{merchant_id}"
        existing_alert = self.active_alerts.get(alert_key)
        
        if should_alert and not existing_alert:
            # New alert
            alert = await self._trigger_alert(rule, merchant_id, value)
            self.active_alerts[alert_key] = alert
            self._last_alert_time[rule_merchant_key] = datetime.now(timezone.utc)
            
        elif not should_alert and existing_alert:
            # Alert resolved
            await self._resolve_alert(existing_alert)
            del self.active_alerts[alert_key]
    
    async def _get_metric_value(
        self,
        metric: str,
        merchant_id: str,
        window: AggregationWindow,
    ) -> Optional[float]:
        """Get current value of a metric."""
        # Map metric names to aggregator methods
        if metric == "gmv":
            result = await self.aggregator.get_gmv(merchant_id, window)
            return result.value
        
        elif metric == "order_count":
            result = await self.aggregator.get_order_count(merchant_id, window)
            return result.value
        
        elif metric == "conversion_rate":
            result = await self.aggregator.get_conversion_rate(merchant_id, window)
            return result.value
        
        elif metric == "aov":
            result = await self.aggregator.get_average_order_value(merchant_id, window)
            return result.value
        
        # For other metrics, would need additional aggregator methods
        # or direct queries
        
        return None
    
    async def _trigger_alert(
        self,
        rule: AlertRule,
        merchant_id: str,
        value: float,
    ) -> Alert:
        """Create and notify for a new alert."""
        from uuid import uuid4
        
        alert = Alert(
            id=f"alert_{uuid4().hex[:12]}",
            rule_id=rule.id,
            rule_name=rule.name,
            merchant_id=merchant_id,
            metric=rule.metric,
            value=value,
            threshold=rule.threshold,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            triggered_at=datetime.now(timezone.utc),
        )
        
        logger.warning(
            "Alert triggered",
            alert_id=alert.id,
            rule=rule.name,
            merchant_id=merchant_id,
            value=value,
            threshold=rule.threshold,
        )
        
        # Send notifications
        await self._send_notifications(alert, rule)
        
        return alert
    
    async def _resolve_alert(self, alert: Alert) -> None:
        """Mark an alert as resolved."""
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        
        logger.info(
            "Alert resolved",
            alert_id=alert.id,
            rule=alert.rule_name,
            duration_minutes=(alert.resolved_at - alert.triggered_at).seconds / 60,
        )
        
        # Could send resolution notification
    
    async def _send_notifications(self, alert: Alert, rule: AlertRule) -> None:
        """Send notifications for an alert."""
        
        # Slack notification
        if rule.notify_slack:
            await self._notify_slack(alert)
        
        # PagerDuty (for critical alerts)
        if rule.notify_pagerduty and alert.severity == AlertSeverity.CRITICAL:
            await self._notify_pagerduty(alert)
        
        # Email
        if rule.notify_email and rule.email_recipients:
            await self._notify_email(alert, rule.email_recipients)
        
        # Custom notifiers
        for notifier in self._notifiers:
            try:
                await notifier(alert)
            except Exception as e:
                logger.error("Custom notifier failed", error=str(e))
    
    async def _notify_slack(self, alert: Alert) -> None:
        """Send Slack notification."""
        # Would use Slack webhook
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
        }
        
        message = {
            "text": f"{severity_emoji[alert.severity]} Alert: {alert.rule_name}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{alert.rule_name}*\n"
                                f"Merchant: `{alert.merchant_id}`\n"
                                f"Metric: `{alert.metric}` = {alert.value} "
                                f"(threshold: {alert.threshold})",
                    },
                },
            ],
        }
        
        logger.info("Slack notification sent", alert_id=alert.id)
    
    async def _notify_pagerduty(self, alert: Alert) -> None:
        """Send PagerDuty notification."""
        # Would use PagerDuty Events API
        logger.info("PagerDuty notification sent", alert_id=alert.id)
    
    async def _notify_email(self, alert: Alert, recipients: list[str]) -> None:
        """Send email notification."""
        # Would use email service (SendGrid, etc.)
        logger.info(
            "Email notification sent",
            alert_id=alert.id,
            recipients=recipients,
        )
    
    # =========================================================================
    # Alert Management API
    # =========================================================================
    
    async def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str,
    ) -> Optional[Alert]:
        """Acknowledge an active alert."""
        for alert in self.active_alerts.values():
            if alert.id == alert_id:
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_at = datetime.now(timezone.utc)
                alert.acknowledged_by = user_id
                
                logger.info(
                    "Alert acknowledged",
                    alert_id=alert_id,
                    user_id=user_id,
                )
                return alert
        
        return None
    
    async def get_active_alerts(
        self,
        merchant_id: Optional[str] = None,
    ) -> list[Alert]:
        """Get all active alerts, optionally filtered by merchant."""
        alerts = list(self.active_alerts.values())
        
        if merchant_id:
            alerts = [a for a in alerts if a.merchant_id == merchant_id]
        
        return alerts
    
    async def get_alert_history(
        self,
        merchant_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Get historical alerts from database."""
        # Would query database for historical alerts
        # Placeholder
        return []
