"""
Unit tests for Catalyst Recommendation Predictor.
"""

import pytest

from src.catalyst.predictor import (
    RecommendationPlacement,
    RecommendationPredictor,
    RecommendationRequest,
    RecommendationStrategy,
)


class TestRecommendationPredictor:
    """Tests for RecommendationPredictor class."""
    
    @pytest.fixture
    def predictor(self):
        """Create predictor instance."""
        return RecommendationPredictor()
    
    @pytest.mark.asyncio
    async def test_get_recommendations_returns_products(self, predictor):
        """Test that recommendations are returned."""
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id="user_456",
            anonymous_id=None,
            placement=RecommendationPlacement.HOMEPAGE,
            limit=5,
        )
        
        response = await predictor.get_recommendations(request)
        
        assert len(response.product_ids) <= 5
        assert len(response.scores) == len(response.product_ids)
        assert response.request_id.startswith("rec_")
    
    @pytest.mark.asyncio
    async def test_pdp_recommendations_with_source_product(self, predictor):
        """Test PDP recommendations use source product."""
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id=None,
            anonymous_id="anon_789",
            placement=RecommendationPlacement.PDP,
            limit=10,
            source_product_id="prod_abc",
        )
        
        response = await predictor.get_recommendations(request)
        
        # Source product should not be in recommendations
        assert "prod_abc" not in response.product_ids
    
    @pytest.mark.asyncio
    async def test_cart_recommendations_exclude_cart_items(self, predictor):
        """Test cart recommendations exclude items in cart."""
        cart_items = ["prod_1", "prod_2", "prod_3"]
        
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id="user_456",
            anonymous_id=None,
            placement=RecommendationPlacement.CART,
            limit=5,
            cart_product_ids=cart_items,
            exclude_product_ids=cart_items,
        )
        
        response = await predictor.get_recommendations(request)
        
        # Cart items should not be in recommendations
        for cart_item in cart_items:
            assert cart_item not in response.product_ids
    
    def test_determine_strategy_homepage_with_user(self, predictor):
        """Test strategy selection for homepage with logged-in user."""
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id="user_456",
            anonymous_id=None,
            placement=RecommendationPlacement.HOMEPAGE,
            limit=10,
        )
        
        strategy = predictor._determine_strategy(request)
        
        assert strategy == RecommendationStrategy.COLLABORATIVE
    
    def test_determine_strategy_homepage_anonymous(self, predictor):
        """Test strategy selection for anonymous homepage visitor."""
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id=None,
            anonymous_id="anon_789",
            placement=RecommendationPlacement.HOMEPAGE,
            limit=10,
        )
        
        strategy = predictor._determine_strategy(request)
        
        assert strategy == RecommendationStrategy.POPULARITY
    
    def test_determine_strategy_pdp_with_source(self, predictor):
        """Test strategy selection for PDP with source product."""
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id=None,
            anonymous_id="anon_789",
            placement=RecommendationPlacement.PDP,
            limit=10,
            source_product_id="prod_xyz",
        )
        
        strategy = predictor._determine_strategy(request)
        
        assert strategy == RecommendationStrategy.CONTENT_BASED
    
    @pytest.mark.asyncio
    async def test_popularity_fallback(self, predictor):
        """Test popularity fallback returns results."""
        request = RecommendationRequest(
            merchant_id="merch_123",
            user_id=None,
            anonymous_id=None,
            placement=RecommendationPlacement.HOMEPAGE,
            limit=10,
        )
        
        product_ids, scores = await predictor._popularity_recommend(request)
        
        assert len(product_ids) > 0
        assert len(scores) == len(product_ids)
        # Scores should be descending
        assert scores == sorted(scores, reverse=True)
    
    def test_response_to_dict(self, predictor):
        """Test response serialization."""
        from src.catalyst.predictor import RecommendationResponse
        
        response = RecommendationResponse(
            product_ids=["prod_1", "prod_2"],
            scores=[0.9, 0.8],
            strategy=RecommendationStrategy.COLLABORATIVE,
            model_version="v2.3.1",
            latency_ms=25.5,
            request_id="rec_abc123",
            placement=RecommendationPlacement.PDP,
        )
        
        result = response.to_dict()
        
        assert result["product_ids"] == ["prod_1", "prod_2"]
        assert result["strategy"] == "collaborative"
        assert result["placement"] == "pdp"
