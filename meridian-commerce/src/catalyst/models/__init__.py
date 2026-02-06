"""
Catalyst ML Models

Implementation of various recommendation model architectures.

Models:
- Collaborative Filtering (Matrix Factorization, Neural CF)
- Content-Based (Embedding similarity)
- Hybrid (Combining collaborative and content signals)
"""

from src.catalyst.models.collaborative import CollaborativeFilteringModel
from src.catalyst.models.content_based import ContentBasedModel

__all__ = [
    "CollaborativeFilteringModel",
    "ContentBasedModel",
]
