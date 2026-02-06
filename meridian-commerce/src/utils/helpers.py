"""
Helper utilities used across the Meridian Commerce platform.

Contains common utility functions for data processing, formatting,
and validation that are used by multiple modules.
"""

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, TypeVar
from uuid import uuid4

T = TypeVar("T")


# =============================================================================
# ID Generation
# =============================================================================

def generate_id(prefix: str = "") -> str:
    """
    Generate a unique ID with optional prefix.
    
    Args:
        prefix: Optional prefix (e.g., "order", "cust", "prod")
    
    Returns:
        Unique ID string
    
    Examples:
        >>> generate_id("order")
        'order_a1b2c3d4e5f6'
    """
    uid = uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{uid}"
    return uid


def generate_request_id() -> str:
    """Generate request ID for tracing."""
    return f"req_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"


# =============================================================================
# Currency & Number Formatting
# =============================================================================

def format_currency(
    amount: Decimal | float | int,
    currency: str = "USD",
    include_symbol: bool = True,
) -> str:
    """
    Format amount as currency string.
    
    Args:
        amount: Monetary amount
        currency: Currency code (default USD)
        include_symbol: Whether to include currency symbol
    
    Returns:
        Formatted currency string
    """
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    
    # Round to 2 decimal places
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "CAD": "C$",
    }
    
    formatted = f"{amount:,.2f}"
    
    if include_symbol:
        symbol = symbols.get(currency, currency)
        return f"{symbol}{formatted}"
    
    return formatted


def calculate_change_percent(
    current: Decimal | float,
    previous: Decimal | float,
) -> float:
    """
    Calculate percentage change between two values.
    
    Returns 0 if previous is 0 to avoid division by zero.
    """
    if previous == 0:
        return 0.0
    
    return float(((current - previous) / previous) * 100)


# =============================================================================
# Date & Time Utilities  
# =============================================================================

def now_utc() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime, fmt: str = "iso") -> str:
    """
    Format datetime to string.
    
    Args:
        dt: Datetime to format
        fmt: Format type - "iso", "date", "datetime", "epoch"
    
    Returns:
        Formatted string
    """
    if fmt == "iso":
        return dt.isoformat()
    elif fmt == "date":
        return dt.strftime("%Y-%m-%d")
    elif fmt == "datetime":
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    elif fmt == "epoch":
        return str(int(dt.timestamp()))
    else:
        return dt.strftime(fmt)


# =============================================================================
# String Utilities
# =============================================================================

def slugify(text: str) -> str:
    """
    Convert text to URL-safe slug.
    
    Args:
        text: Input text
    
    Returns:
        Slugified string
    """
    # Lowercase and replace spaces
    slug = text.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove non-alphanumeric (except hyphens)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Trim hyphens from ends
    return slug.strip("-")


def mask_pii(text: str, visible_chars: int = 4) -> str:
    """
    Mask personally identifiable information.
    
    Args:
        text: Text to mask
        visible_chars: Number of characters to leave visible
    
    Returns:
        Masked string
    """
    if len(text) <= visible_chars:
        return "*" * len(text)
    
    return text[:visible_chars] + "*" * (len(text) - visible_chars)


def mask_email(email: str) -> str:
    """Mask email address for privacy."""
    if "@" not in email:
        return mask_pii(email)
    
    local, domain = email.rsplit("@", 1)
    masked_local = mask_pii(local, 2)
    return f"{masked_local}@{domain}"


# =============================================================================
# Data Processing
# =============================================================================

def chunk_list(items: List[T], chunk_size: int) -> List[List[T]]:
    """
    Split list into chunks.
    
    Args:
        items: List to chunk
        chunk_size: Maximum items per chunk
    
    Returns:
        List of chunks
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def deep_merge(base: Dict, override: Dict) -> Dict:
    """
    Deep merge two dictionaries.
    
    Override values take precedence.
    """
    result = base.copy()
    
    for key, value in override.items():
        if (
            key in result 
            and isinstance(result[key], dict) 
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def safe_get(d: Dict, keys: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary value.
    
    Args:
        d: Dictionary to search
        keys: Dot-separated key path (e.g., "user.profile.email")
        default: Default value if not found
    
    Returns:
        Value or default
    """
    current = d
    
    for key in keys.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


# =============================================================================
# Hashing & Security
# =============================================================================

def hash_string(text: str, algorithm: str = "sha256") -> str:
    """
    Hash a string.
    
    Args:
        text: String to hash
        algorithm: Hash algorithm (sha256, md5, etc.)
    
    Returns:
        Hex digest
    """
    hasher = hashlib.new(algorithm)
    hasher.update(text.encode("utf-8"))
    return hasher.hexdigest()


def generate_api_key(prefix: str = "mc") -> str:
    """
    Generate API key with prefix.
    
    Format: {prefix}_{env}_{random}
    e.g., mc_live_a1b2c3d4e5f6g7h8
    """
    random_part = uuid4().hex[:16]
    return f"{prefix}_live_{random_part}"


# =============================================================================
# Validation
# =============================================================================

def is_valid_email(email: str) -> bool:
    """Check if email format is valid."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def is_valid_merchant_id(merchant_id: str) -> bool:
    """Validate merchant ID format."""
    return bool(
        merchant_id 
        and merchant_id.startswith("merch_")
        and len(merchant_id) == 18
    )
