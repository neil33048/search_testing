"""
Forge - Data Pipeline Framework

Forge orchestrates all data pipelines for the Meridian Commerce platform.
Handles batch ETL, incremental syncs, and table materialization.

Pipeline types:
- Batch: Nightly full refreshes (dim tables, aggregates)
- Incremental: Real-time/hourly updates (fact tables)
- Streaming: Continuous processing from Kinesis

Key pipelines:
- fact_orders: Order-level transactions
- fact_events: Beacon event data
- dim_customers: Customer dimension with LTV/tier
- dim_products: Product catalog with embeddings
- agg_daily_gmv: Daily GMV aggregates

Schedule:
- Nightly batch runs at 02:00 UTC
- Hourly incremental syncs for fact tables
- Monthly customer tier recalculation
"""

from src.forge.pipeline import Pipeline, PipelineStatus
from src.forge.extractors.base import BaseExtractor
from src.forge.transformers.base import BaseTransformer
from src.forge.loaders.base import BaseLoader

__all__ = [
    "Pipeline",
    "PipelineStatus",
    "BaseExtractor",
    "BaseTransformer", 
    "BaseLoader",
]
