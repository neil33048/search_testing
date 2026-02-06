"""
Test fixtures for merchants.

Provides sample merchant data for unit and integration tests.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal


@pytest.fixture
def bronze_merchant():
    """Bronze tier merchant fixture."""
    return {
        "id": "merch_bronze_test",
        "name": "Test Bronze Store",
        "slug": "test-bronze-store",
        "tier": "bronze",
        "industry": "electronics",
        "status": "active",
        "contact_email": "admin@bronzestore.com",
        "gmv_mtd": Decimal("8500.00"),
        "gmv_12m": Decimal("85000.00"),
        "created_at": datetime(2023, 6, 15, tzinfo=timezone.utc),
    }


@pytest.fixture
def silver_merchant():
    """Silver tier merchant fixture."""
    return {
        "id": "merch_silver_test",
        "name": "Test Silver Boutique",
        "slug": "test-silver-boutique",
        "tier": "silver",
        "industry": "apparel",
        "status": "active",
        "contact_email": "admin@silverboutique.com",
        "gmv_mtd": Decimal("35000.00"),
        "gmv_12m": Decimal("350000.00"),
        "created_at": datetime(2022, 3, 1, tzinfo=timezone.utc),
    }


@pytest.fixture
def gold_merchant():
    """Gold tier merchant fixture."""
    return {
        "id": "merch_gold_test",
        "name": "Test Gold Emporium",
        "slug": "test-gold-emporium",
        "tier": "gold",
        "industry": "home_garden",
        "status": "active",
        "contact_email": "admin@goldemporium.com",
        "gmv_mtd": Decimal("125000.00"),
        "gmv_12m": Decimal("1200000.00"),
        "created_at": datetime(2021, 9, 10, tzinfo=timezone.utc),
    }


@pytest.fixture  
def platinum_merchant():
    """Platinum tier merchant fixture (highest tier)."""
    return {
        "id": "merch_platinum_test",
        "name": "Test Platinum Megastore",
        "slug": "test-platinum-megastore",
        "tier": "platinum",
        "industry": "sports_outdoors",
        "status": "active",
        "contact_email": "admin@platinummega.com",
        "gmv_mtd": Decimal("450000.00"),
        "gmv_12m": Decimal("4500000.00"),
        "created_at": datetime(2020, 1, 5, tzinfo=timezone.utc),
    }


@pytest.fixture
def suspended_merchant():
    """Suspended merchant fixture for testing edge cases."""
    return {
        "id": "merch_suspended_test",
        "name": "Test Suspended Store",
        "slug": "test-suspended-store",
        "tier": "bronze",
        "industry": "beauty",
        "status": "suspended",
        "contact_email": "admin@suspendedstore.com",
        "gmv_mtd": Decimal("0.00"),
        "gmv_12m": Decimal("45000.00"),
        "suspension_reason": "payment_failure",
        "created_at": datetime(2023, 2, 20, tzinfo=timezone.utc),
    }


@pytest.fixture
def all_merchants(
    bronze_merchant,
    silver_merchant,
    gold_merchant,
    platinum_merchant,
):
    """All active merchants fixture."""
    return [
        bronze_merchant,
        silver_merchant,
        gold_merchant,
        platinum_merchant,
    ]


# Merchant tier thresholds (annual GMV)
TIER_THRESHOLDS = {
    "platinum": Decimal("2000000.00"),  # $2M+
    "gold": Decimal("500000.00"),        # $500K-$2M
    "silver": Decimal("100000.00"),      # $100K-$500K
    "bronze": Decimal("0.00"),           # <$100K
}

# Legacy tier mapping (old system used tier1-tier4)
# tier1 = Platinum, tier2 = Gold, tier3 = Silver, tier4 = Bronze
LEGACY_TIER_MAP = {
    "tier1": "platinum",
    "tier2": "gold",
    "tier3": "silver",
    "tier4": "bronze",
}
