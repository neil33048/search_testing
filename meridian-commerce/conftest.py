"""
pytest configuration and shared fixtures for Meridian Commerce tests.

This file is automatically loaded by pytest and provides fixtures
available to all tests in the project.
"""

import asyncio
import os
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

# Import test fixtures
from tests.fixtures.merchants import *


# =============================================================================
# Environment Setup
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def set_test_environment():
    """Set test environment variables."""
    os.environ["MERIDIAN_ENV"] = "test"
    os.environ["MERIDIAN_DEBUG"] = "true"
    os.environ["MERIDIAN_LOG_LEVEL"] = "DEBUG"
    yield
    # Cleanup if needed


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
async def db_session():
    """
    Create a test database session.
    
    Uses transactions that are rolled back after each test.
    """
    from src.core.database import async_session_maker
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_db():
    """Mock database for unit tests that don't need real DB."""
    mock = Mock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    return mock


# =============================================================================
# Cache Fixtures
# =============================================================================

@pytest.fixture
def mock_cache():
    """Mock Redis cache for unit tests."""
    cache = Mock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    cache.exists = AsyncMock(return_value=False)
    return cache


# =============================================================================
# API Fixtures
# =============================================================================

@pytest.fixture
def api_key():
    """Test API key."""
    return "mc_test_abcd1234efgh5678"


@pytest.fixture
def auth_headers(api_key):
    """Authorization headers for API requests."""
    return {"Authorization": f"Bearer {api_key}"}


@pytest.fixture
def sample_event():
    """Sample event for Beacon tests."""
    return {
        "merchant_id": "merch_test123456",
        "event_type": "page_view",
        "properties": {
            "page_path": "/products/test-product",
            "page_title": "Test Product",
        },
        "context": {
            "user_agent": "Mozilla/5.0 Test",
            "ip": "127.0.0.1",
        },
        "session_id": "sess_test123",
        "anonymous_id": "anon_test456",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_order():
    """Sample order for pipeline tests."""
    return {
        "id": "order_test123456",
        "merchant_id": "merch_test123456",
        "customer_id": "cust_test789012",
        "status": "confirmed",
        "subtotal": Decimal("99.99"),
        "tax_amount": Decimal("8.00"),
        "shipping_amount": Decimal("5.99"),
        "total_amount": Decimal("113.98"),
        "item_count": 2,
        "created_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_product():
    """Sample product for Catalyst tests."""
    return {
        "id": "prod_test123456",
        "merchant_id": "merch_test123456",
        "name": "Test Product",
        "slug": "test-product",
        "sku": "SKU-TEST-001",
        "price": Decimal("49.99"),
        "status": "active",
        "inventory_quantity": 100,
        "category_path": "Electronics > Gadgets",
        "created_at": datetime.now(timezone.utc),
    }


# =============================================================================
# Time Fixtures
# =============================================================================

@pytest.fixture
def frozen_time():
    """Freeze time for deterministic tests."""
    from unittest.mock import patch
    
    fixed_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    with patch("src.utils.helpers.now_utc", return_value=fixed_time):
        yield fixed_time


# =============================================================================
# Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires external services)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
