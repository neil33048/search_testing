"""
Custom exception hierarchy for Meridian Commerce Platform.

All application-specific exceptions inherit from MeridianError.
These exceptions are caught by API middleware and converted to
appropriate HTTP responses.

Exception codes follow the pattern: MC-{COMPONENT}-{NUMBER}
- MC-API-xxx: API layer errors
- MC-BEA-xxx: Beacon errors
- MC-PUL-xxx: Pulse errors  
- MC-CAT-xxx: Catalyst errors
- MC-FOR-xxx: Forge errors
"""

from typing import Any, Optional


class MeridianError(Exception):
    """
    Base exception for all Meridian Commerce errors.
    
    Attributes:
        message: Human-readable error message
        code: Error code for tracking/debugging (e.g., MC-API-001)
        details: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code or "MC-ERR-000"
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": {
                "message": self.message,
                "code": self.code,
                "details": self.details,
            }
        }


# =============================================================================
# HTTP-Related Exceptions
# =============================================================================

class NotFoundError(MeridianError):
    """Resource not found (HTTP 404)."""
    
    def __init__(
        self,
        resource: str,
        identifier: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with ID '{identifier}' not found"
        super().__init__(message, "MC-API-404", details)
        self.resource = resource
        self.identifier = identifier


class ValidationError(MeridianError):
    """Request validation failed (HTTP 400)."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        code = "MC-API-400"
        if field:
            details = details or {}
            details["field"] = field
        super().__init__(message, code, details)
        self.field = field


class AuthenticationError(MeridianError):
    """Authentication failed (HTTP 401)."""
    
    def __init__(
        self,
        message: str = "Authentication required",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, "MC-API-401", details)


class AuthorizationError(MeridianError):
    """
    Authorization failed (HTTP 403).
    
    Raised when user is authenticated but lacks permission
    for the requested action.
    """
    
    def __init__(
        self,
        message: str = "Permission denied",
        required_permission: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        if required_permission:
            details = details or {}
            details["required_permission"] = required_permission
        super().__init__(message, "MC-API-403", details)


class RateLimitError(MeridianError):
    """
    Rate limit exceeded (HTTP 429).
    
    Includes retry-after information for clients.
    """
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: int = 60,
        details: Optional[dict[str, Any]] = None,
    ):
        details = details or {}
        details["retry_after_seconds"] = retry_after_seconds
        super().__init__(message, "MC-API-429", details)
        self.retry_after_seconds = retry_after_seconds


class ConflictError(MeridianError):
    """Resource conflict (HTTP 409)."""
    
    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message, "MC-API-409", details)


# =============================================================================
# Beacon Exceptions
# =============================================================================

class BeaconError(MeridianError):
    """Base exception for Beacon event collection system."""
    pass


class EventValidationError(BeaconError):
    """
    Event failed schema validation.
    
    Raised when an incoming event doesn't match expected schema.
    In strict mode, this causes the event to be rejected.
    In non-strict mode, the event is logged and dropped.
    """
    
    def __init__(
        self,
        message: str,
        event_type: Optional[str] = None,
        validation_errors: Optional[list[dict]] = None,
    ):
        details = {}
        if event_type:
            details["event_type"] = event_type
        if validation_errors:
            details["validation_errors"] = validation_errors
        super().__init__(message, "MC-BEA-001", details)


class EventIngestionError(BeaconError):
    """Failed to ingest event to Kinesis."""
    
    def __init__(
        self,
        message: str,
        event_id: Optional[str] = None,
    ):
        details = {"event_id": event_id} if event_id else {}
        super().__init__(message, "MC-BEA-002", details)


class UnknownEventTypeError(BeaconError):
    """
    Unknown event type received.
    
    Raised when allow_unknown_events is False and an unrecognized
    event type is received.
    """
    
    def __init__(self, event_type: str):
        super().__init__(
            f"Unknown event type: {event_type}",
            "MC-BEA-003",
            {"event_type": event_type},
        )


# =============================================================================
# Pulse Exceptions
# =============================================================================

class PulseError(MeridianError):
    """Base exception for Pulse analytics system."""
    pass


class AggregationError(PulseError):
    """Failed to compute aggregation."""
    
    def __init__(
        self,
        message: str,
        metric: Optional[str] = None,
    ):
        details = {"metric": metric} if metric else {}
        super().__init__(message, "MC-PUL-001", details)


class DashboardCacheError(PulseError):
    """Dashboard cache operation failed."""
    
    def __init__(
        self,
        message: str,
        merchant_id: Optional[str] = None,
    ):
        details = {"merchant_id": merchant_id} if merchant_id else {}
        super().__init__(message, "MC-PUL-002", details)


# =============================================================================
# Catalyst Exceptions
# =============================================================================

class CatalystError(MeridianError):
    """Base exception for Catalyst recommendation engine."""
    pass


class ModelNotFoundError(CatalystError):
    """
    Requested model version not found.
    
    Can occur during model deployment if version doesn't exist
    or hasn't been promoted to serving.
    """
    
    def __init__(self, model_version: str):
        super().__init__(
            f"Model version '{model_version}' not found",
            "MC-CAT-001",
            {"model_version": model_version},
        )


class InsufficientDataError(CatalystError):
    """
    Insufficient data for recommendations.
    
    Raised when a user has too few interactions for
    collaborative filtering. Triggers fallback strategy.
    """
    
    def __init__(
        self,
        user_id: str,
        interaction_count: int,
        required_count: int,
    ):
        super().__init__(
            f"User has insufficient interactions for recommendations",
            "MC-CAT-002",
            {
                "user_id": user_id,
                "interaction_count": interaction_count,
                "required_count": required_count,
            },
        )


class ModelServingError(CatalystError):
    """Model serving endpoint error."""
    
    def __init__(
        self,
        message: str,
        endpoint: Optional[str] = None,
    ):
        details = {"endpoint": endpoint} if endpoint else {}
        super().__init__(message, "MC-CAT-003", details)


class FeatureStoreError(CatalystError):
    """Failed to retrieve features from feature store."""
    
    def __init__(self, message: str, feature_names: Optional[list[str]] = None):
        details = {"feature_names": feature_names} if feature_names else {}
        super().__init__(message, "MC-CAT-004", details)


# =============================================================================
# Forge Exceptions
# =============================================================================

class ForgeError(MeridianError):
    """Base exception for Forge data pipeline system."""
    pass


class PipelineExecutionError(ForgeError):
    """Pipeline execution failed."""
    
    def __init__(
        self,
        message: str,
        pipeline_name: Optional[str] = None,
        stage: Optional[str] = None,
    ):
        details = {}
        if pipeline_name:
            details["pipeline_name"] = pipeline_name
        if stage:
            details["stage"] = stage
        super().__init__(message, "MC-FOR-001", details)


class ExtractorError(ForgeError):
    """Data extraction failed."""
    
    def __init__(
        self,
        message: str,
        source: Optional[str] = None,
    ):
        details = {"source": source} if source else {}
        super().__init__(message, "MC-FOR-002", details)


class TransformerError(ForgeError):
    """Data transformation failed."""
    
    def __init__(
        self,
        message: str,
        transformer: Optional[str] = None,
    ):
        details = {"transformer": transformer} if transformer else {}
        super().__init__(message, "MC-FOR-003", details)


class LoaderError(ForgeError):
    """Data loading failed."""
    
    def __init__(
        self,
        message: str,
        destination: Optional[str] = None,
    ):
        details = {"destination": destination} if destination else {}
        super().__init__(message, "MC-FOR-004", details)


class CheckpointError(ForgeError):
    """
    Pipeline checkpoint operation failed.
    
    Checkpoints are used for recovery in long-running pipelines.
    """
    
    def __init__(
        self,
        message: str,
        checkpoint_id: Optional[str] = None,
    ):
        details = {"checkpoint_id": checkpoint_id} if checkpoint_id else {}
        super().__init__(message, "MC-FOR-005", details)


# =============================================================================
# Data Warehouse Exceptions
# =============================================================================

class WarehouseError(MeridianError):
    """Base exception for data warehouse operations."""
    pass


class SnowflakeError(WarehouseError):
    """Snowflake-specific error."""
    
    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
    ):
        # Don't include full query in production for security
        details = {}
        if query:
            # Truncate query for logging
            details["query_preview"] = query[:200] if len(query) > 200 else query
        super().__init__(message, "MC-WH-001", details)


class BigQueryError(WarehouseError):
    """
    BigQuery-specific error.
    
    Note: BigQuery is legacy - used only for some historical reports.
    New development should use Snowflake.
    """
    
    def __init__(
        self,
        message: str,
        job_id: Optional[str] = None,
    ):
        details = {"job_id": job_id} if job_id else {}
        super().__init__(message, "MC-WH-002", details)


# =============================================================================
# Customer/Merchant Exceptions
# =============================================================================

class CustomerNotFoundError(NotFoundError):
    """Customer not found."""
    
    def __init__(self, customer_id: str):
        super().__init__("Customer", customer_id)


class MerchantNotFoundError(NotFoundError):
    """Merchant not found."""
    
    def __init__(self, merchant_id: str):
        super().__init__("Merchant", merchant_id)


class OrderNotFoundError(NotFoundError):
    """Order not found."""
    
    def __init__(self, order_id: str):
        super().__init__("Order", order_id)


class ProductNotFoundError(NotFoundError):
    """Product not found."""
    
    def __init__(self, product_id: str):
        super().__init__("Product", product_id)


# =============================================================================
# Tier/SLA Exceptions
# =============================================================================

class TierViolationError(MeridianError):
    """
    Operation not allowed for customer's tier.
    
    Some features are restricted to higher tiers (Gold, Platinum).
    """
    
    def __init__(
        self,
        message: str,
        current_tier: str,
        required_tier: str,
    ):
        super().__init__(
            message,
            "MC-TIER-001",
            {
                "current_tier": current_tier,
                "required_tier": required_tier,
            },
        )
