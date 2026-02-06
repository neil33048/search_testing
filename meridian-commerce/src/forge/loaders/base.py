"""
Forge Loaders - Base Classes

Loaders write transformed data to destination systems.
Each loader type handles a specific destination.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class BaseLoader(ABC):
    """
    Base class for all data loaders.
    
    Loaders write transformed data to destination systems
    such as data warehouses, databases, or file storage.
    """
    
    @abstractmethod
    async def load(
        self,
        records: list[dict],
    ) -> int:
        """
        Load records to the destination.
        
        Args:
            records: Records to load
            
        Returns:
            Number of records loaded
        """
        pass
    
    @abstractmethod
    async def validate(self) -> bool:
        """
        Validate the loader configuration and connectivity.
        
        Returns:
            True if validation passes
        """
        pass


class SnowflakeLoader(BaseLoader):
    """
    Load data to Snowflake data warehouse.
    
    Primary loader for the Meridian lakehouse.
    Supports both full replace and merge/upsert patterns.
    """
    
    def __init__(
        self,
        table: str,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        warehouse: str = "COMPUTE_WH",
        write_mode: str = "append",  # append, replace, merge
        merge_keys: Optional[list[str]] = None,
    ):
        self.table = table
        self.database = database
        self.schema = schema
        self.warehouse = warehouse
        self.write_mode = write_mode
        self.merge_keys = merge_keys or []
    
    async def load(self, records: list[dict]) -> int:
        """Load records to Snowflake."""
        if not records:
            return 0
        
        logger.info(
            "Loading to Snowflake",
            table=self.table,
            record_count=len(records),
            mode=self.write_mode,
        )
        
        # Would use snowflake-connector-python
        # Different strategies based on write_mode:
        # - append: INSERT INTO table ...
        # - replace: TRUNCATE + INSERT
        # - merge: MERGE INTO table USING ...
        
        if self.write_mode == "merge" and self.merge_keys:
            # Merge/upsert pattern
            pass
        elif self.write_mode == "replace":
            # Full replace
            pass
        else:
            # Default append
            pass
        
        return len(records)
    
    async def validate(self) -> bool:
        """Validate Snowflake connection and table access."""
        return True


class PostgresLoader(BaseLoader):
    """
    Load data to PostgreSQL.
    
    Used for loading operational data back to the
    transactional database.
    """
    
    def __init__(
        self,
        table: str,
        connection_string: Optional[str] = None,
        write_mode: str = "append",
        conflict_columns: Optional[list[str]] = None,
    ):
        self.table = table
        self.connection_string = connection_string
        self.write_mode = write_mode
        self.conflict_columns = conflict_columns or []
    
    async def load(self, records: list[dict]) -> int:
        """Load records to PostgreSQL."""
        if not records:
            return 0
        
        logger.info(
            "Loading to PostgreSQL",
            table=self.table,
            record_count=len(records),
        )
        
        # Would use asyncpg or psycopg2
        # INSERT ... ON CONFLICT for upsert
        
        return len(records)
    
    async def validate(self) -> bool:
        """Validate PostgreSQL connection."""
        return True


class S3Loader(BaseLoader):
    """
    Load data to S3 as Parquet files.
    
    Used for archival and data lake storage.
    Partitions by date by default.
    """
    
    def __init__(
        self,
        bucket: str,
        prefix: str,
        file_format: str = "parquet",
        partition_columns: Optional[list[str]] = None,
        compression: str = "snappy",
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.file_format = file_format
        self.partition_columns = partition_columns or []
        self.compression = compression
    
    async def load(self, records: list[dict]) -> int:
        """Load records to S3."""
        if not records:
            return 0
        
        logger.info(
            "Loading to S3",
            bucket=self.bucket,
            prefix=self.prefix,
            format=self.file_format,
        )
        
        # Would use boto3 + pyarrow/pandas
        # Partitioned by date: s3://bucket/prefix/date=2024-01-15/file.parquet
        
        return len(records)
    
    async def validate(self) -> bool:
        """Validate S3 access."""
        return True


class ClickHouseLoader(BaseLoader):
    """
    Load data to ClickHouse.
    
    Used for loading aggregated data for Pulse analytics.
    """
    
    def __init__(
        self,
        table: str,
        database: str = "default",
        host: Optional[str] = None,
    ):
        self.table = table
        self.database = database
        self.host = host
    
    async def load(self, records: list[dict]) -> int:
        """Load records to ClickHouse."""
        if not records:
            return 0
        
        logger.info(
            "Loading to ClickHouse",
            table=self.table,
            record_count=len(records),
        )
        
        # Would use clickhouse-driver
        # INSERT INTO table FORMAT JSONEachRow
        
        return len(records)
    
    async def validate(self) -> bool:
        """Validate ClickHouse connection."""
        return True


class RedisLoader(BaseLoader):
    """
    Load data to Redis cache.
    
    Used for caching lookup data and aggregates
    for fast API access.
    """
    
    def __init__(
        self,
        key_template: str,  # e.g., "customer:{customer_id}"
        key_field: str,
        ttl: Optional[int] = None,
    ):
        self.key_template = key_template
        self.key_field = key_field
        self.ttl = ttl
    
    async def load(self, records: list[dict]) -> int:
        """Load records to Redis."""
        if not records:
            return 0
        
        logger.info(
            "Loading to Redis",
            key_template=self.key_template,
            record_count=len(records),
        )
        
        # Would use redis-py
        # Pipeline for bulk inserts
        
        return len(records)
    
    async def validate(self) -> bool:
        """Validate Redis connection."""
        return True


class MultiLoader(BaseLoader):
    """
    Load to multiple destinations.
    
    Useful for writing to both warehouse and cache.
    """
    
    def __init__(self, loaders: list[BaseLoader]):
        self.loaders = loaders
    
    async def load(self, records: list[dict]) -> int:
        """Load records to all destinations."""
        import asyncio
        
        tasks = [loader.load(records) for loader in self.loaders]
        results = await asyncio.gather(*tasks)
        
        return sum(results)
    
    async def validate(self) -> bool:
        """Validate all loaders."""
        import asyncio
        
        results = await asyncio.gather(
            *[loader.validate() for loader in self.loaders]
        )
        return all(results)
