"""
Catalyst Recommendation Predictor

Real-time recommendation serving with low latency requirements.
Target: <50ms p99 latency.

Supports multiple recommendation placements:
- PDP (Product Detail Page): "Customers also bought"
- Cart: "Complete your order"
- Homepage: Personalized picks
- Category: Top items in category
- Email: Personalized email recommendations
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import structlog

from config.settings import settings
from src.core.cache import CatalystCacheManager
from src.core.exceptions import (
    CatalystError,
    InsufficientDataError,
    ModelServingError,
)

logger = structlog.get_logger(__name__)


class RecommendationPlacement(str, Enum):
    """Where recommendations are displayed."""
    PDP = "pdp"              # Product detail page
    CART = "cart"            # Cart page
    HOMEPAGE = "homepage"    # Homepage
    CATEGORY = "category"    # Category listing
    SEARCH = "search"        # Search results
    EMAIL = "email"          # Email campaigns
    CHECKOUT = "checkout"    # Checkout page


class RecommendationStrategy(str, Enum):
    """Strategy used to generate recommendations."""
    COLLABORATIVE = "collaborative"
    CONTENT_BASED = "content_based"
    POPULARITY = "popularity"
    HYBRID = "hybrid"


@dataclass
class RecommendationRequest:
    """Request for recommendations."""
    
    merchant_id: str
    user_id: Optional[str]
    anonymous_id: Optional[str]
    placement: RecommendationPlacement
    limit: int = 10
    
    # Context
    source_product_id: Optional[str] = None  # For PDP recs
    cart_product_ids: Optional[list[str]] = None  # For cart recs
    category_id: Optional[str] = None  # For category recs
    
    # Filters
    exclude_product_ids: Optional[list[str]] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    in_stock_only: bool = True


@dataclass
class RecommendationResponse:
    """Response containing recommendations."""
    
    product_ids: list[str]
    scores: list[float]
    strategy: RecommendationStrategy
    model_version: str
    latency_ms: float
    
    # Metadata for tracking
    request_id: str
    placement: RecommendationPlacement
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "product_ids": self.product_ids,
            "scores": self.scores,
            "strategy": self.strategy.value,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "placement": self.placement.value,
        }


class RecommendationPredictor:
    """
    Serves real-time product recommendations.
    
    Uses a tiered fallback approach:
    1. Collaborative filtering (if user has sufficient history)
    2. Content-based (if source product available)
    3. Popularity (always available)
    
    Usage:
        predictor = RecommendationPredictor()
        
        response = await predictor.get_recommendations(
            RecommendationRequest(
                merchant_id="merch_123",
                user_id="user_456",
                placement=RecommendationPlacement.PDP,
                source_product_id="prod_789",
            )
        )
    """
    
    def __init__(self):
        self.cache = CatalystCacheManager()
        self.model_version = settings.catalyst.model_version
        self._request_count = 0
        
        # Lazy-loaded model clients
        self._collaborative_model = None
        self._content_model = None
        self._popularity_model = None
    
    async def get_recommendations(
        self,
        request: RecommendationRequest,
    ) -> RecommendationResponse:
        """
        Get personalized recommendations.
        
        Applies fallback strategy based on available data:
        1. Try collaborative filtering if user has history
        2. Fall back to content-based if source product provided
        3. Use popularity as final fallback
        """
        start_time = time.perf_counter()
        request_id = self._generate_request_id()
        self._request_count += 1
        
        # Check cache first
        cached = await self._check_cache(request)
        if cached:
            latency = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Cache hit for recommendations",
                request_id=request_id,
                latency_ms=latency,
            )
            return RecommendationResponse(
                product_ids=cached,
                scores=[1.0] * len(cached),  # Cache doesn't preserve scores
                strategy=RecommendationStrategy.COLLABORATIVE,
                model_version=self.model_version,
                latency_ms=latency,
                request_id=request_id,
                placement=request.placement,
            )
        
        # Try strategies in order of preference
        strategy = self._determine_strategy(request)
        
        try:
            if strategy == RecommendationStrategy.COLLABORATIVE:
                product_ids, scores = await self._collaborative_recommend(request)
            elif strategy == RecommendationStrategy.CONTENT_BASED:
                product_ids, scores = await self._content_based_recommend(request)
            elif strategy == RecommendationStrategy.HYBRID:
                product_ids, scores = await self._hybrid_recommend(request)
            else:
                product_ids, scores = await self._popularity_recommend(request)
                
        except InsufficientDataError:
            # Fall back to popularity
            logger.info(
                "Insufficient data, falling back to popularity",
                request_id=request_id,
                original_strategy=strategy.value,
            )
            strategy = RecommendationStrategy.POPULARITY
            product_ids, scores = await self._popularity_recommend(request)
        
        except ModelServingError as e:
            # Model serving failed, fall back
            logger.error(
                "Model serving failed",
                request_id=request_id,
                error=str(e),
            )
            strategy = RecommendationStrategy.POPULARITY
            product_ids, scores = await self._popularity_recommend(request)
        
        # Apply filters
        product_ids, scores = self._apply_filters(
            product_ids, scores, request
        )
        
        # Limit results
        product_ids = product_ids[:request.limit]
        scores = scores[:request.limit]
        
        # Cache results
        await self._cache_results(request, product_ids)
        
        latency = (time.perf_counter() - start_time) * 1000
        
        logger.info(
            "Recommendations generated",
            request_id=request_id,
            strategy=strategy.value,
            count=len(product_ids),
            latency_ms=round(latency, 2),
        )
        
        return RecommendationResponse(
            product_ids=product_ids,
            scores=scores,
            strategy=strategy,
            model_version=self.model_version,
            latency_ms=round(latency, 2),
            request_id=request_id,
            placement=request.placement,
        )
    
    def _determine_strategy(
        self,
        request: RecommendationRequest,
    ) -> RecommendationStrategy:
        """
        Determine which strategy to use based on request context.
        
        Logic:
        - Logged-in user with history -> collaborative
        - Source product provided -> content-based or hybrid
        - Anonymous user -> popularity
        """
        configured_fallback = settings.catalyst.fallback_strategy
        
        # Homepage personalization needs user history
        if request.placement == RecommendationPlacement.HOMEPAGE:
            if request.user_id:
                return RecommendationStrategy.COLLABORATIVE
            else:
                return RecommendationStrategy.POPULARITY
        
        # PDP uses content-based similarity
        if request.placement == RecommendationPlacement.PDP:
            if request.source_product_id:
                if request.user_id:
                    return RecommendationStrategy.HYBRID
                return RecommendationStrategy.CONTENT_BASED
        
        # Cart completion uses collaborative
        if request.placement == RecommendationPlacement.CART:
            if request.user_id or request.cart_product_ids:
                return RecommendationStrategy.COLLABORATIVE
        
        # Default based on settings
        if configured_fallback == "hybrid":
            return RecommendationStrategy.HYBRID
        elif configured_fallback == "content_based":
            return RecommendationStrategy.CONTENT_BASED
        else:
            return RecommendationStrategy.POPULARITY
    
    async def _collaborative_recommend(
        self,
        request: RecommendationRequest,
    ) -> tuple[list[str], list[float]]:
        """
        Generate recommendations using collaborative filtering.
        
        Uses user-item interaction matrix to find similar users
        and recommend items they purchased.
        """
        user_id = request.user_id or request.anonymous_id
        
        # Check if user has enough interactions
        interaction_count = await self._get_user_interaction_count(
            request.merchant_id, user_id
        )
        
        if interaction_count < settings.catalyst.min_interactions:
            raise InsufficientDataError(
                user_id=user_id,
                interaction_count=interaction_count,
                required_count=settings.catalyst.min_interactions,
            )
        
        # Call model serving endpoint
        # In production, this would call TensorFlow Serving, TorchServe, etc.
        predictions = await self._call_model_serving(
            model_type="collaborative",
            inputs={
                "user_id": user_id,
                "merchant_id": request.merchant_id,
                "n_recommendations": request.limit * 2,  # Get extra for filtering
            },
        )
        
        return predictions["product_ids"], predictions["scores"]
    
    async def _content_based_recommend(
        self,
        request: RecommendationRequest,
    ) -> tuple[list[str], list[float]]:
        """
        Generate recommendations using content-based similarity.
        
        Uses product embeddings to find similar items based on
        attributes like category, brand, description, etc.
        """
        if not request.source_product_id:
            # Need a source product for content-based
            return await self._popularity_recommend(request)
        
        # Get similar products based on embeddings
        predictions = await self._call_model_serving(
            model_type="content_based",
            inputs={
                "product_id": request.source_product_id,
                "merchant_id": request.merchant_id,
                "n_recommendations": request.limit * 2,
            },
        )
        
        return predictions["product_ids"], predictions["scores"]
    
    async def _hybrid_recommend(
        self,
        request: RecommendationRequest,
    ) -> tuple[list[str], list[float]]:
        """
        Generate recommendations using hybrid approach.
        
        Combines collaborative and content-based signals
        for better recommendations.
        """
        # Get both sets of recommendations in parallel
        collab_task = self._collaborative_recommend(request)
        content_task = self._content_based_recommend(request)
        
        try:
            collab_result, content_result = await asyncio.gather(
                collab_task, content_task
            )
        except InsufficientDataError:
            # Fall back to content-based only
            return await self._content_based_recommend(request)
        
        # Merge results with weighted scoring
        # Collaborative gets higher weight
        merged = {}
        
        for i, (pid, score) in enumerate(zip(*collab_result)):
            merged[pid] = score * 0.7  # 70% weight
        
        for i, (pid, score) in enumerate(zip(*content_result)):
            if pid in merged:
                merged[pid] += score * 0.3
            else:
                merged[pid] = score * 0.3
        
        # Sort by combined score
        sorted_items = sorted(merged.items(), key=lambda x: x[1], reverse=True)
        
        product_ids = [pid for pid, _ in sorted_items]
        scores = [score for _, score in sorted_items]
        
        return product_ids, scores
    
    async def _popularity_recommend(
        self,
        request: RecommendationRequest,
    ) -> tuple[list[str], list[float]]:
        """
        Generate recommendations based on popularity.
        
        Returns bestselling or trending products.
        Always available as fallback.
        """
        # Get popular products for merchant
        # This could be pre-computed and cached
        
        # Simulated popular products
        # In production, would query from aggregated data
        popular_products = [
            ("prod_popular1", 0.95),
            ("prod_popular2", 0.90),
            ("prod_popular3", 0.85),
            ("prod_popular4", 0.80),
            ("prod_popular5", 0.75),
            ("prod_popular6", 0.70),
            ("prod_popular7", 0.65),
            ("prod_popular8", 0.60),
            ("prod_popular9", 0.55),
            ("prod_popular10", 0.50),
        ]
        
        product_ids = [pid for pid, _ in popular_products]
        scores = [score for _, score in popular_products]
        
        return product_ids, scores
    
    async def _call_model_serving(
        self,
        model_type: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Call model serving endpoint.
        
        In production, this would be HTTP call to TensorFlow Serving
        or similar model serving infrastructure.
        """
        endpoint = settings.catalyst.serving_endpoint
        timeout = settings.catalyst.timeout_seconds
        
        # Simulated model response
        # Would use httpx client with timeout
        
        await asyncio.sleep(0.01)  # Simulate network latency
        
        # Return simulated predictions
        return {
            "product_ids": [f"prod_{i:06d}" for i in range(20)],
            "scores": [1.0 - i * 0.05 for i in range(20)],
        }
    
    async def _get_user_interaction_count(
        self,
        merchant_id: str,
        user_id: str,
    ) -> int:
        """Get count of user's historical interactions."""
        # Would query from feature store or database
        # Simulated count
        return 150
    
    def _apply_filters(
        self,
        product_ids: list[str],
        scores: list[float],
        request: RecommendationRequest,
    ) -> tuple[list[str], list[float]]:
        """Apply exclusion and filtering to recommendations."""
        filtered_ids = []
        filtered_scores = []
        
        exclude_set = set(request.exclude_product_ids or [])
        
        # Also exclude source product from PDP recs
        if request.source_product_id:
            exclude_set.add(request.source_product_id)
        
        # Exclude cart items from cart recs
        if request.cart_product_ids:
            exclude_set.update(request.cart_product_ids)
        
        for pid, score in zip(product_ids, scores):
            if pid in exclude_set:
                continue
            
            # Additional filters would check price, stock, etc.
            # from product catalog (would be a service call)
            
            filtered_ids.append(pid)
            filtered_scores.append(score)
        
        return filtered_ids, filtered_scores
    
    async def _check_cache(
        self,
        request: RecommendationRequest,
    ) -> Optional[list[str]]:
        """Check cache for recommendations."""
        user_id = request.user_id or request.anonymous_id
        context = f"{request.placement.value}:{request.source_product_id or ''}"
        
        return await self.cache.get_recommendations(user_id, context)
    
    async def _cache_results(
        self,
        request: RecommendationRequest,
        product_ids: list[str],
    ) -> None:
        """Cache recommendation results."""
        user_id = request.user_id or request.anonymous_id
        context = f"{request.placement.value}:{request.source_product_id or ''}"
        
        await self.cache.cache_recommendations(user_id, product_ids, context)
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID for tracking."""
        from uuid import uuid4
        return f"rec_{uuid4().hex[:12]}"
    
    def get_metrics(self) -> dict[str, Any]:
        """Get predictor metrics."""
        return {
            "request_count": self._request_count,
            "model_version": self.model_version,
        }


class ABTestManager:
    """
    Manages A/B tests for recommendation models.
    
    Allows testing new models or strategies against
    the current production model.
    """
    
    def __init__(self):
        self._active_tests: dict[str, dict] = {}
    
    def create_test(
        self,
        test_id: str,
        control_strategy: RecommendationStrategy,
        treatment_strategy: RecommendationStrategy,
        traffic_split: float = 0.1,  # 10% to treatment
    ) -> None:
        """Create a new A/B test."""
        self._active_tests[test_id] = {
            "control": control_strategy,
            "treatment": treatment_strategy,
            "traffic_split": traffic_split,
            "created_at": time.time(),
        }
    
    def get_assignment(
        self,
        test_id: str,
        user_id: str,
    ) -> RecommendationStrategy:
        """Get A/B test assignment for a user."""
        test = self._active_tests.get(test_id)
        if not test:
            return RecommendationStrategy.COLLABORATIVE
        
        # Deterministic assignment based on user_id hash
        import hashlib
        hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        bucket = (hash_value % 100) / 100
        
        if bucket < test["traffic_split"]:
            return test["treatment"]
        return test["control"]
