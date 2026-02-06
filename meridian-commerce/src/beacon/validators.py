"""
Beacon Event Validators

Validates incoming events against their schemas.
Supports both strict mode (reject invalid events) and
lenient mode (log and pass through).

Validation includes:
- Required fields presence
- Field type checking
- Value constraints (min/max, enums)
- Custom business rules
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import structlog

from src.beacon.schemas import EventSchema, get_schema_for_event_type
from src.models.event import EventType

logger = structlog.get_logger(__name__)


@dataclass
class ValidationError:
    """Single validation error."""
    
    field: str
    message: str
    code: str
    value: Any = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "code": self.code,
            "value": self.value,
        }


@dataclass
class ValidationResult:
    """Result of event validation."""
    
    is_valid: bool
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    
    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(is_valid=True)
    
    @classmethod
    def failure(cls, errors: list[ValidationError]) -> "ValidationResult":
        return cls(
            is_valid=False,
            errors=[e.to_dict() for e in errors],
        )
    
    def add_error(self, error: ValidationError) -> None:
        self.is_valid = False
        self.errors.append(error.to_dict())
    
    def add_warning(self, warning: ValidationError) -> None:
        self.warnings.append(warning.to_dict())


class EventValidator:
    """
    Validates Beacon events against their schemas.
    
    Usage:
        validator = EventValidator()
        result = await validator.validate(
            event_type=EventType.PRODUCT_VIEW,
            properties={"product_id": "prod_123"},
            context={"device": "mobile"},
        )
        
        if not result.is_valid:
            print(result.errors)
    """
    
    def __init__(self):
        # Custom validators for specific business rules
        self._custom_validators: dict[EventType, list[Callable]] = {}
        
        # Register built-in custom validators
        self._register_builtin_validators()
    
    def _register_builtin_validators(self) -> None:
        """Register custom validators for specific event types."""
        
        # Purchase events must have order_id and revenue
        self.register_validator(
            EventType.PURCHASE,
            self._validate_purchase_event,
        )
        
        # Product events must have valid product_id format
        for event_type in [
            EventType.PRODUCT_VIEW,
            EventType.PRODUCT_CLICK,
            EventType.ADD_TO_CART,
        ]:
            self.register_validator(
                event_type,
                self._validate_product_id_format,
            )
    
    def register_validator(
        self,
        event_type: EventType,
        validator: Callable[[dict, dict], Optional[ValidationError]],
    ) -> None:
        """
        Register a custom validator for an event type.
        
        Custom validators receive (properties, context) and return
        a ValidationError if validation fails, None otherwise.
        """
        if event_type not in self._custom_validators:
            self._custom_validators[event_type] = []
        self._custom_validators[event_type].append(validator)
    
    async def validate(
        self,
        event_type: EventType,
        properties: dict[str, Any],
        context: dict[str, Any],
        strict: bool = True,
    ) -> ValidationResult:
        """
        Validate an event against its schema.
        
        Args:
            event_type: Type of event
            properties: Event properties
            context: Event context (device, browser, etc.)
            strict: If True, all errors fail validation.
                    If False, some errors become warnings.
        
        Returns:
            ValidationResult with is_valid flag and any errors/warnings
        """
        result = ValidationResult(is_valid=True)
        
        # Get schema for event type
        schema = get_schema_for_event_type(event_type)
        
        if schema is None:
            if strict:
                result.add_error(ValidationError(
                    field="event_type",
                    message=f"No schema found for event type: {event_type.value}",
                    code="unknown_event_type",
                ))
            return result
        
        # Validate required fields
        self._validate_required_fields(schema, properties, result)
        
        # Validate field types
        self._validate_field_types(schema, properties, result)
        
        # Validate field constraints
        self._validate_constraints(schema, properties, result)
        
        # Validate context
        self._validate_context(context, result)
        
        # Run custom validators
        if event_type in self._custom_validators:
            for validator in self._custom_validators[event_type]:
                error = validator(properties, context)
                if error:
                    if strict:
                        result.add_error(error)
                    else:
                        result.add_warning(error)
        
        if result.is_valid:
            logger.debug(
                "Event validation passed",
                event_type=event_type.value,
            )
        else:
            logger.warning(
                "Event validation failed",
                event_type=event_type.value,
                error_count=len(result.errors),
                errors=result.errors,
            )
        
        return result
    
    def _validate_required_fields(
        self,
        schema: EventSchema,
        properties: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check that all required fields are present."""
        for field_name in schema.required_fields:
            if field_name not in properties:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Required field '{field_name}' is missing",
                    code="required_field_missing",
                ))
            elif properties[field_name] is None:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Required field '{field_name}' cannot be null",
                    code="required_field_null",
                ))
    
    def _validate_field_types(
        self,
        schema: EventSchema,
        properties: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check that fields have correct types."""
        for field_name, expected_type in schema.field_types.items():
            if field_name not in properties:
                continue
            
            value = properties[field_name]
            if value is None:
                continue  # Null handled by required check
            
            if not self._check_type(value, expected_type):
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' should be {expected_type}, got {type(value).__name__}",
                    code="invalid_type",
                    value=value,
                ))
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected = type_map.get(expected_type)
        if expected is None:
            return True  # Unknown type, pass through
        
        return isinstance(value, expected)
    
    def _validate_constraints(
        self,
        schema: EventSchema,
        properties: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Validate field constraints (min, max, enum, etc.)."""
        for field_name, constraints in schema.constraints.items():
            if field_name not in properties:
                continue
            
            value = properties[field_name]
            
            # Min value
            if "min" in constraints and value < constraints["min"]:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' must be at least {constraints['min']}",
                    code="below_minimum",
                    value=value,
                ))
            
            # Max value
            if "max" in constraints and value > constraints["max"]:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' must be at most {constraints['max']}",
                    code="above_maximum",
                    value=value,
                ))
            
            # String length
            if "max_length" in constraints and len(str(value)) > constraints["max_length"]:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' exceeds max length of {constraints['max_length']}",
                    code="max_length_exceeded",
                    value=value,
                ))
            
            # Enum values
            if "enum" in constraints and value not in constraints["enum"]:
                result.add_error(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' must be one of: {constraints['enum']}",
                    code="invalid_enum_value",
                    value=value,
                ))
            
            # Pattern matching
            if "pattern" in constraints:
                import re
                if not re.match(constraints["pattern"], str(value)):
                    result.add_error(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' does not match pattern",
                        code="pattern_mismatch",
                        value=value,
                    ))
    
    def _validate_context(
        self,
        context: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Validate event context."""
        # Context is flexible but we check for known fields
        
        # Validate timestamp if present
        if "timestamp" in context:
            ts = context["timestamp"]
            if isinstance(ts, str):
                try:
                    from datetime import datetime
                    datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    result.add_warning(ValidationError(
                        field="context.timestamp",
                        message="Invalid timestamp format",
                        code="invalid_timestamp",
                        value=ts,
                    ))
    
    # ==========================================================================
    # Custom Validators
    # ==========================================================================
    
    def _validate_purchase_event(
        self,
        properties: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[ValidationError]:
        """Validate purchase event has required fields."""
        if "order_id" not in properties:
            return ValidationError(
                field="order_id",
                message="Purchase events must have order_id",
                code="missing_order_id",
            )
        
        if "revenue" not in properties:
            return ValidationError(
                field="revenue",
                message="Purchase events must have revenue",
                code="missing_revenue",
            )
        
        revenue = properties.get("revenue")
        if revenue is not None and revenue < 0:
            return ValidationError(
                field="revenue",
                message="Revenue cannot be negative",
                code="negative_revenue",
                value=revenue,
            )
        
        return None
    
    def _validate_product_id_format(
        self,
        properties: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[ValidationError]:
        """Validate product_id has correct format."""
        product_id = properties.get("product_id")
        
        if product_id is None:
            return ValidationError(
                field="product_id",
                message="Product events must have product_id",
                code="missing_product_id",
            )
        
        # Accept both our format (prod_xxx) and merchant's own IDs
        # But log warning for non-standard format
        if not str(product_id).startswith("prod_") and len(str(product_id)) > 50:
            return ValidationError(
                field="product_id",
                message="Product ID exceeds maximum length of 50 characters",
                code="product_id_too_long",
                value=product_id,
            )
        
        return None


class SchemaRegistry:
    """
    Registry for event schemas.
    
    Schemas can be loaded from files or registered programmatically.
    This allows merchants to define custom event schemas.
    """
    
    _instance: Optional["SchemaRegistry"] = None
    
    def __new__(cls) -> "SchemaRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._schemas = {}
            cls._instance._loaded = False
        return cls._instance
    
    def register(self, event_type: EventType, schema: EventSchema) -> None:
        """Register a schema for an event type."""
        self._schemas[event_type] = schema
    
    def get(self, event_type: EventType) -> Optional[EventSchema]:
        """Get schema for an event type."""
        return self._schemas.get(event_type)
    
    def load_from_config(self, config_path: str) -> None:
        """Load schemas from a configuration file."""
        # Placeholder - would load from YAML/JSON
        pass
