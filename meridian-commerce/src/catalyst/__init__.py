"""
Catalyst - ML Recommendation Engine

Catalyst powers personalized product recommendations across
Meridian Commerce merchant storefronts.

Recommendation strategies:
- Collaborative Filtering: Based on user-item interactions
- Content-Based: Based on product attributes and embeddings
- Popularity: Fallback based on trending/bestselling items
- Hybrid: Combination of above strategies

Key metrics:
- CTR (Click-Through Rate) on recommendations
- Recommendation revenue attribution
- Model latency (p50, p99)
- Coverage (% of catalog recommended)

Architecture:
- trainer.py: Model training and evaluation
- predictor.py: Real-time serving
- models/: Model implementations
"""

from src.catalyst.predictor import RecommendationPredictor
from src.catalyst.trainer import ModelTrainer

__all__ = [
    "RecommendationPredictor",
    "ModelTrainer",
]
