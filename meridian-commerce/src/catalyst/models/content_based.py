"""
Content-Based Recommendation Model

Recommends items based on similarity of item attributes,
not user behavior. Useful for:
- Cold-start items (new products with no interactions)
- Similar item recommendations ("More like this")
- Diversity in recommendations

Uses product embeddings from:
- Text (title, description) via sentence transformers
- Images via CNN/CLIP
- Categorical features (brand, category)
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ItemFeatures:
    """Features for content-based recommendations."""
    
    item_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    tags: Optional[list[str]] = None
    
    # Pre-computed embeddings
    text_embedding: Optional[np.ndarray] = None
    image_embedding: Optional[np.ndarray] = None


class ContentBasedModel:
    """
    Content-based recommendation model.
    
    Uses item attributes and embeddings to find similar items.
    Does not require user interaction history.
    
    Features used:
    - Text embeddings (from title + description)
    - Category hierarchy
    - Brand
    - Price range
    - Tags
    
    Similarity metrics:
    - Cosine similarity for embeddings
    - Jaccard for categorical features
    - Gaussian kernel for price
    
    Usage:
        model = ContentBasedModel()
        model.fit(item_features_list)
        
        similar = model.get_similar_items("prod_123", n=10)
    """
    
    def __init__(
        self,
        embedding_dim: int = 384,  # sentence-transformers default
        use_text: bool = True,
        use_category: bool = True,
        use_brand: bool = True,
        use_price: bool = True,
        text_weight: float = 0.5,
        category_weight: float = 0.2,
        brand_weight: float = 0.15,
        price_weight: float = 0.15,
    ):
        self.embedding_dim = embedding_dim
        self.use_text = use_text
        self.use_category = use_category
        self.use_brand = use_brand
        self.use_price = use_price
        
        # Weights for combining similarities
        self.text_weight = text_weight
        self.category_weight = category_weight
        self.brand_weight = brand_weight
        self.price_weight = price_weight
        
        # Normalize weights
        total_weight = text_weight + category_weight + brand_weight + price_weight
        self.text_weight /= total_weight
        self.category_weight /= total_weight
        self.brand_weight /= total_weight
        self.price_weight /= total_weight
        
        # Item data
        self.items: dict[str, ItemFeatures] = {}
        self.item_ids: list[str] = []
        
        # Pre-computed for fast similarity
        self.text_embeddings: Optional[np.ndarray] = None
        self.category_matrix: Optional[np.ndarray] = None
        self.brand_matrix: Optional[np.ndarray] = None
        self.prices: Optional[np.ndarray] = None
        
        # Encodings for categorical features
        self.category_encoder: dict[str, int] = {}
        self.brand_encoder: dict[str, int] = {}
        
        self._is_fitted = False
    
    def fit(
        self,
        items: list[ItemFeatures],
    ) -> None:
        """
        Fit the model on item features.
        
        Builds similarity indices for fast retrieval.
        
        Args:
            items: List of item features
        """
        logger.info("Fitting content-based model", n_items=len(items))
        
        self.items = {item.item_id: item for item in items}
        self.item_ids = [item.item_id for item in items]
        n_items = len(items)
        
        # Build text embedding matrix
        if self.use_text:
            self.text_embeddings = np.zeros((n_items, self.embedding_dim))
            for i, item in enumerate(items):
                if item.text_embedding is not None:
                    self.text_embeddings[i] = item.text_embedding
                else:
                    # Would generate embedding here using sentence transformer
                    # Placeholder: random embedding
                    self.text_embeddings[i] = np.random.randn(self.embedding_dim)
            
            # Normalize for cosine similarity
            norms = np.linalg.norm(self.text_embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            self.text_embeddings /= norms
        
        # Build category encoding
        if self.use_category:
            categories = set(item.category for item in items if item.category)
            self.category_encoder = {cat: idx for idx, cat in enumerate(categories)}
            
            n_categories = len(self.category_encoder)
            self.category_matrix = np.zeros((n_items, n_categories))
            
            for i, item in enumerate(items):
                if item.category and item.category in self.category_encoder:
                    cat_idx = self.category_encoder[item.category]
                    self.category_matrix[i, cat_idx] = 1.0
        
        # Build brand encoding
        if self.use_brand:
            brands = set(item.brand for item in items if item.brand)
            self.brand_encoder = {brand: idx for idx, brand in enumerate(brands)}
            
            n_brands = len(self.brand_encoder)
            self.brand_matrix = np.zeros((n_items, n_brands))
            
            for i, item in enumerate(items):
                if item.brand and item.brand in self.brand_encoder:
                    brand_idx = self.brand_encoder[item.brand]
                    self.brand_matrix[i, brand_idx] = 1.0
        
        # Store prices
        if self.use_price:
            self.prices = np.array([
                item.price if item.price else 0.0
                for item in items
            ])
            
            # Normalize prices for similarity calculation
            price_mean = np.mean(self.prices[self.prices > 0])
            price_std = np.std(self.prices[self.prices > 0])
            if price_std > 0:
                self.prices = (self.prices - price_mean) / price_std
        
        self._is_fitted = True
        
        logger.info(
            "Content-based model fitted",
            n_items=n_items,
            n_categories=len(self.category_encoder),
            n_brands=len(self.brand_encoder),
        )
    
    def get_similar_items(
        self,
        item_id: str,
        n: int = 10,
        exclude_items: Optional[list[str]] = None,
    ) -> tuple[list[str], list[float]]:
        """
        Get items similar to the given item.
        
        Uses weighted combination of different similarity types.
        
        Args:
            item_id: Source item ID
            n: Number of similar items
            exclude_items: Items to exclude from results
            
        Returns:
            Tuple of (item_ids, similarity_scores)
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        
        if item_id not in self.items:
            logger.warning("Item not found", item_id=item_id)
            return [], []
        
        # Get index of source item
        source_idx = self.item_ids.index(item_id)
        
        # Compute similarities
        similarities = np.zeros(len(self.item_ids))
        
        if self.use_text and self.text_embeddings is not None:
            # Cosine similarity for text embeddings
            text_sim = self.text_embeddings @ self.text_embeddings[source_idx]
            similarities += self.text_weight * text_sim
        
        if self.use_category and self.category_matrix is not None:
            # Jaccard-like similarity for category (0 or 1)
            source_category = self.category_matrix[source_idx]
            cat_sim = (self.category_matrix * source_category).sum(axis=1)
            similarities += self.category_weight * cat_sim
        
        if self.use_brand and self.brand_matrix is not None:
            # Brand match similarity
            source_brand = self.brand_matrix[source_idx]
            brand_sim = (self.brand_matrix * source_brand).sum(axis=1)
            similarities += self.brand_weight * brand_sim
        
        if self.use_price and self.prices is not None:
            # Gaussian kernel for price similarity
            source_price = self.prices[source_idx]
            price_diff = np.abs(self.prices - source_price)
            price_sim = np.exp(-price_diff ** 2 / 2)  # Gaussian kernel
            similarities += self.price_weight * price_sim
        
        # Build exclusion set
        exclude_set = set(exclude_items or [])
        exclude_set.add(item_id)  # Always exclude source item
        
        # Get top-n
        sorted_indices = np.argsort(-similarities)
        
        similar_ids = []
        similar_scores = []
        
        for idx in sorted_indices:
            candidate_id = self.item_ids[idx]
            
            if candidate_id in exclude_set:
                continue
            
            similar_ids.append(candidate_id)
            similar_scores.append(float(similarities[idx]))
            
            if len(similar_ids) >= n:
                break
        
        return similar_ids, similar_scores
    
    def get_items_for_query(
        self,
        query_embedding: np.ndarray,
        n: int = 10,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        price_range: Optional[tuple[float, float]] = None,
    ) -> tuple[list[str], list[float]]:
        """
        Get items matching a query embedding.
        
        Useful for text search or image search.
        
        Args:
            query_embedding: Query vector
            n: Number of results
            category: Filter by category
            brand: Filter by brand
            price_range: Filter by price (min, max)
            
        Returns:
            Tuple of (item_ids, scores)
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        
        # Normalize query
        query_norm = np.linalg.norm(query_embedding)
        if query_norm > 0:
            query_embedding = query_embedding / query_norm
        
        # Compute similarity with all items
        if self.text_embeddings is not None:
            similarities = self.text_embeddings @ query_embedding
        else:
            similarities = np.zeros(len(self.item_ids))
        
        # Apply filters
        valid_mask = np.ones(len(self.item_ids), dtype=bool)
        
        if category and self.use_category:
            if category in self.category_encoder:
                cat_idx = self.category_encoder[category]
                valid_mask &= self.category_matrix[:, cat_idx] == 1
        
        if brand and self.use_brand:
            if brand in self.brand_encoder:
                brand_idx = self.brand_encoder[brand]
                valid_mask &= self.brand_matrix[:, brand_idx] == 1
        
        if price_range and self.prices is not None:
            min_price, max_price = price_range
            # Denormalize prices for comparison
            # (This is simplified - would need actual denormalization)
            valid_mask &= (self.prices >= min_price) & (self.prices <= max_price)
        
        # Apply mask
        similarities[~valid_mask] = -np.inf
        
        # Get top-n
        sorted_indices = np.argsort(-similarities)[:n]
        
        item_ids = [self.item_ids[idx] for idx in sorted_indices]
        scores = [float(similarities[idx]) for idx in sorted_indices]
        
        # Filter out -inf scores
        valid_results = [(iid, score) for iid, score in zip(item_ids, scores) 
                        if score > -np.inf]
        
        if valid_results:
            item_ids, scores = zip(*valid_results)
            return list(item_ids), list(scores)
        return [], []
    
    def add_item(self, item: ItemFeatures) -> None:
        """
        Add a new item to the model.
        
        Useful for incremental updates without full retraining.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        
        self.items[item.item_id] = item
        self.item_ids.append(item.item_id)
        
        # Add to matrices
        if self.use_text:
            if item.text_embedding is not None:
                embedding = item.text_embedding / np.linalg.norm(item.text_embedding)
            else:
                embedding = np.random.randn(self.embedding_dim)
                embedding /= np.linalg.norm(embedding)
            
            self.text_embeddings = np.vstack([self.text_embeddings, embedding])
        
        # Add to category matrix
        if self.use_category:
            new_row = np.zeros((1, len(self.category_encoder)))
            if item.category in self.category_encoder:
                new_row[0, self.category_encoder[item.category]] = 1.0
            self.category_matrix = np.vstack([self.category_matrix, new_row])
        
        # Add to brand matrix  
        if self.use_brand:
            new_row = np.zeros((1, len(self.brand_encoder)))
            if item.brand in self.brand_encoder:
                new_row[0, self.brand_encoder[item.brand]] = 1.0
            self.brand_matrix = np.vstack([self.brand_matrix, new_row])
        
        # Add price
        if self.use_price:
            self.prices = np.append(self.prices, item.price or 0.0)
        
        logger.debug("Item added to content model", item_id=item.item_id)
