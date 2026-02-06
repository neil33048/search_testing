"""
Integration tests for data pipeline flow.

Tests end-to-end data flow from extraction through loading.
Requires test database and warehouse connections.
"""

import pytest
from datetime import datetime, date

from src.forge.pipeline import Pipeline, PipelineConfig
from src.forge.extractors.base import BaseExtractor
from src.forge.transformers.base import BaseTransformer
from src.forge.loaders.base import BaseLoader


@pytest.mark.integration
class TestPipelineFlow:
    """Integration tests for complete pipeline flow."""
    
    @pytest.fixture
    def pipeline_config(self):
        """Pipeline configuration for tests."""
        return PipelineConfig(
            name="test_orders_pipeline",
            source="test_postgres",
            destination="test_warehouse",
            schedule=None,  # Manual trigger for tests
            retries=0,
        )
    
    @pytest.fixture
    def sample_orders(self):
        """Sample order data for testing."""
        return [
            {
                "id": "order_test_001",
                "merchant_id": "merch_test",
                "customer_id": "cust_test_1",
                "status": "delivered",
                "subtotal": 150.00,
                "tax_amount": 12.00,
                "shipping_amount": 5.99,
                "total_amount": 167.99,
                "created_at": datetime(2024, 1, 15, 10, 30, 0),
            },
            {
                "id": "order_test_002",
                "merchant_id": "merch_test",
                "customer_id": "cust_test_2",
                "status": "shipped",
                "subtotal": 89.99,
                "tax_amount": 7.20,
                "shipping_amount": 0.00,
                "total_amount": 97.19,
                "created_at": datetime(2024, 1, 15, 14, 45, 0),
            },
        ]
    
    @pytest.mark.asyncio
    async def test_extract_transform_load_flow(
        self, pipeline_config, sample_orders
    ):
        """Test complete ETL flow."""
        pipeline = Pipeline(pipeline_config)
        
        # Run pipeline with sample data
        result = await pipeline.run(
            source_data=sample_orders,
            run_date=date(2024, 1, 15),
        )
        
        assert result.status == "success"
        assert result.rows_processed == len(sample_orders)
        assert result.errors == []
    
    @pytest.mark.asyncio
    async def test_pipeline_handles_empty_data(self, pipeline_config):
        """Test pipeline handles empty source data gracefully."""
        pipeline = Pipeline(pipeline_config)
        
        result = await pipeline.run(
            source_data=[],
            run_date=date(2024, 1, 15),
        )
        
        assert result.status == "success"
        assert result.rows_processed == 0
    
    @pytest.mark.asyncio
    async def test_pipeline_tracks_metrics(self, pipeline_config, sample_orders):
        """Test pipeline tracks execution metrics."""
        pipeline = Pipeline(pipeline_config)
        
        result = await pipeline.run(
            source_data=sample_orders,
            run_date=date(2024, 1, 15),
        )
        
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds > 0
        assert result.bytes_processed > 0


@pytest.mark.integration
class TestExtractorConnections:
    """Integration tests for extractor connections."""
    
    @pytest.mark.asyncio
    async def test_postgres_connection(self):
        """Test PostgreSQL connection works."""
        extractor = BaseExtractor.create("postgres", {
            "host": "localhost",
            "port": 5432,
            "database": "meridian_test",
        })
        
        # Should not raise
        await extractor.validate_connection()
    
    @pytest.mark.asyncio
    async def test_incremental_extraction(self):
        """Test incremental extraction by timestamp."""
        extractor = BaseExtractor.create("postgres", {
            "host": "localhost",
            "port": 5432,
            "database": "meridian_test",
        })
        
        since = datetime(2024, 1, 14, 0, 0, 0)
        
        data = await extractor.extract(
            table="orders",
            incremental_column="updated_at",
            since=since,
        )
        
        # All records should be after the since timestamp
        for row in data:
            assert row["updated_at"] >= since


@pytest.mark.integration
class TestLoaderConnections:
    """Integration tests for loader connections."""
    
    @pytest.mark.asyncio
    async def test_snowflake_connection(self):
        """Test Snowflake connection works."""
        loader = BaseLoader.create("snowflake", {
            "account": "test_account",
            "warehouse": "test_wh",
            "database": "meridian_test",
        })
        
        # Should not raise
        await loader.validate_connection()
    
    @pytest.mark.asyncio
    async def test_upsert_mode(self):
        """Test upsert mode updates existing records."""
        loader = BaseLoader.create("snowflake", {
            "account": "test_account",
            "warehouse": "test_wh",
            "database": "meridian_test",
        })
        
        data = [
            {"id": "test_001", "value": 100},
            {"id": "test_002", "value": 200},
        ]
        
        result = await loader.load(
            data=data,
            table="test_table",
            mode="upsert",
            key_columns=["id"],
        )
        
        assert result.rows_affected == len(data)
