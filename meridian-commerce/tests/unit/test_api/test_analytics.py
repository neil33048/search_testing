"""
Unit tests for Analytics API routes.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from src.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Auth headers for API requests."""
    return {"Authorization": "Bearer mc_test_key_123"}


class TestDashboardEndpoint:
    """Tests for /analytics/dashboard endpoint."""
    
    def test_dashboard_returns_widgets(self, client, auth_headers):
        """Test dashboard returns all widgets."""
        response = client.get(
            "/api/v1/analytics/dashboard",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "widgets" in data
        assert "generated_at" in data
    
    def test_dashboard_with_window_param(self, client, auth_headers):
        """Test dashboard with different time windows."""
        for window in ["realtime", "hourly", "daily", "weekly"]:
            response = client.get(
                "/api/v1/analytics/dashboard",
                params={"window": window},
                headers=auth_headers,
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["window"] == window
    
    def test_dashboard_requires_auth(self, client):
        """Test dashboard requires authentication."""
        response = client.get("/api/v1/analytics/dashboard")
        
        assert response.status_code == 401


class TestGMVEndpoint:
    """Tests for /analytics/gmv endpoint."""
    
    def test_gmv_returns_data(self, client, auth_headers):
        """Test GMV endpoint returns data."""
        response = client.get(
            "/api/v1/analytics/gmv",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "current_value" in data
        assert "previous_value" in data
        assert "change_percent" in data
    
    def test_gmv_with_breakdown(self, client, auth_headers):
        """Test GMV with breakdown dimension."""
        response = client.get(
            "/api/v1/analytics/gmv",
            params={"breakdown": "category"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if "breakdown" in data:
            assert isinstance(data["breakdown"], list)


class TestConversionFunnelEndpoint:
    """Tests for /analytics/funnel endpoint."""
    
    def test_funnel_returns_stages(self, client, auth_headers):
        """Test funnel returns conversion stages."""
        response = client.get(
            "/api/v1/analytics/funnel",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "stages" in data
        assert len(data["stages"]) > 0
        
        # Verify stage structure
        first_stage = data["stages"][0]
        assert "name" in first_stage
        assert "count" in first_stage
    
    def test_funnel_stages_order(self, client, auth_headers):
        """Test funnel stages are in expected order."""
        response = client.get(
            "/api/v1/analytics/funnel",
            headers=auth_headers,
        )
        
        data = response.json()
        stage_names = [s["name"] for s in data["stages"]]
        
        # Expected order for e-commerce funnel
        expected_order = [
            "page_view",
            "product_view", 
            "add_to_cart",
            "checkout_started",
            "order_completed",
        ]
        
        # At least first stages should match
        for i, expected in enumerate(expected_order[:len(stage_names)]):
            assert stage_names[i] == expected


class TestRealtimeEndpoint:
    """Tests for /analytics/realtime endpoint."""
    
    def test_realtime_returns_live_data(self, client, auth_headers):
        """Test realtime endpoint returns live metrics."""
        response = client.get(
            "/api/v1/analytics/realtime",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "active_visitors" in data
        assert "events_per_minute" in data
    
    def test_realtime_includes_hot_products(self, client, auth_headers):
        """Test realtime includes trending products."""
        response = client.get(
            "/api/v1/analytics/realtime",
            headers=auth_headers,
        )
        
        data = response.json()
        
        if "hot_products" in data:
            assert isinstance(data["hot_products"], list)
