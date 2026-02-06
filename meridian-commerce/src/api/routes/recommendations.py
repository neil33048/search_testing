"""
Recommendations API endpoints (Catalyst).

Provides ML-powered product recommendations
for various placements and contexts.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.middleware.auth import get_current_merchant
from src.catalyst.predictor import (
    RecommendationPlacement,
    RecommendationPredictor,
    RecommendationRequest,
)

router = APIRouter()

# Predictor instance (would use DI in production)
predictor = RecommendationPredictor()


class RecommendationRequestBody(BaseModel):
    """Request body for recommendations."""
    
    user_id: Optional[str] = Field(None, description="Logged-in user ID")
    anonymous_id: Optional[str] = Field(None, description="Anonymous visitor ID")
    placement: str = Field("pdp", description="Recommendation placement")
    limit: int = Field(10, ge=1, le=50, description="Number of recommendations")
    
    # Context
    source_product_id: Optional[str] = Field(None, description="Source product for PDP recs")
    cart_product_ids: Optional[list[str]] = Field(None, description="Products in cart")
    category_id: Optional[str] = Field(None, description="Current category")
    
    # Filters
    exclude_product_ids: Optional[list[str]] = Field(None, description="Products to exclude")
    price_min: Optional[float] = Field(None, description="Minimum price filter")
    price_max: Optional[float] = Field(None, description="Maximum price filter")
    in_stock_only: bool = Field(True, description="Only recommend in-stock products")


@router.post("")
async def get_recommendations(
    request: RecommendationRequestBody,
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get personalized product recommendations.
    
    Recommendations are generated using ML models based on:
    - User purchase history (collaborative filtering)
    - Product similarity (content-based)
    - Trending items (popularity)
    
    Placement types:
    - pdp: Product detail page ("Customers also bought")
    - cart: Shopping cart ("Complete your order")
    - homepage: Personalized picks
    - category: Top in category
    - email: Email campaign recommendations
    - checkout: Checkout page suggestions
    
    The API automatically selects the best strategy based on
    available data and placement context.
    """
    # Map placement string to enum
    placement_map = {
        "pdp": RecommendationPlacement.PDP,
        "cart": RecommendationPlacement.CART,
        "homepage": RecommendationPlacement.HOMEPAGE,
        "category": RecommendationPlacement.CATEGORY,
        "search": RecommendationPlacement.SEARCH,
        "email": RecommendationPlacement.EMAIL,
        "checkout": RecommendationPlacement.CHECKOUT,
    }
    placement = placement_map.get(request.placement, RecommendationPlacement.PDP)
    
    # Build request
    rec_request = RecommendationRequest(
        merchant_id=merchant_id,
        user_id=request.user_id,
        anonymous_id=request.anonymous_id,
        placement=placement,
        limit=request.limit,
        source_product_id=request.source_product_id,
        cart_product_ids=request.cart_product_ids,
        category_id=request.category_id,
        exclude_product_ids=request.exclude_product_ids,
        price_min=request.price_min,
        price_max=request.price_max,
        in_stock_only=request.in_stock_only,
    )
    
    response = await predictor.get_recommendations(rec_request)
    return response.to_dict()


@router.get("/similar/{product_id}")
async def get_similar_products(
    product_id: str,
    limit: int = Query(10, ge=1, le=50),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get products similar to the specified product.
    
    Uses content-based similarity based on:
    - Product category
    - Brand
    - Description embeddings
    - Price range
    """
    request = RecommendationRequest(
        merchant_id=merchant_id,
        user_id=None,
        anonymous_id=None,
        placement=RecommendationPlacement.PDP,
        limit=limit,
        source_product_id=product_id,
    )
    
    response = await predictor.get_recommendations(request)
    return response.to_dict()


@router.get("/popular")
async def get_popular_products(
    category_id: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(10, ge=1, le=50),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get popular/trending products.
    
    Returns bestselling products based on recent order volume.
    Useful as fallback when personalization isn't possible.
    """
    request = RecommendationRequest(
        merchant_id=merchant_id,
        user_id=None,
        anonymous_id=None,
        placement=RecommendationPlacement.HOMEPAGE,
        limit=limit,
        category_id=category_id,
    )
    
    # Force popularity strategy
    response = await predictor._popularity_recommend(request)
    product_ids, scores = response
    
    return {
        "product_ids": product_ids[:limit],
        "scores": scores[:limit],
        "strategy": "popularity",
    }


@router.get("/cart-completion")
async def get_cart_completion(
    cart_product_ids: str = Query(..., description="Comma-separated product IDs in cart"),
    user_id: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    merchant_id: str = Depends(get_current_merchant),
) -> dict[str, Any]:
    """
    Get recommendations to complete the cart.
    
    Suggests products frequently purchased together with
    items already in the cart.
    """
    cart_items = [p.strip() for p in cart_product_ids.split(",")]
    
    request = RecommendationRequest(
        merchant_id=merchant_id,
        user_id=user_id,
        anonymous_id=None,
        placement=RecommendationPlacement.CART,
        limit=limit,
        cart_product_ids=cart_items,
        exclude_product_ids=cart_items,  # Don't recommend items already in cart
    )
    
    response = await predictor.get_recommendations(request)
    return response.to_dict()
