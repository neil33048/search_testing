"""
Forge Transformers - Base Classes

Transformers apply business logic to extracted data.
Each transformer handles a specific type of transformation.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class BaseTransformer(ABC):
    """
    Base class for all data transformers.
    
    Transformers receive data from extractors and apply
    business logic transformations.
    """
    
    @abstractmethod
    async def transform(
        self,
        records: list[dict],
    ) -> list[dict]:
        """
        Transform records.
        
        Args:
            records: Input records
            
        Returns:
            Transformed records
        """
        pass


class ColumnMapper(BaseTransformer):
    """
    Map and rename columns.
    
    Usage:
        mapper = ColumnMapper({
            "old_name": "new_name",
            "cust_id": "customer_id",
        })
    """
    
    def __init__(
        self,
        mapping: dict[str, str],
        drop_unmapped: bool = False,
    ):
        self.mapping = mapping
        self.drop_unmapped = drop_unmapped
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Apply column mapping."""
        result = []
        
        for record in records:
            new_record = {}
            
            for old_key, value in record.items():
                if old_key in self.mapping:
                    new_record[self.mapping[old_key]] = value
                elif not self.drop_unmapped:
                    new_record[old_key] = value
            
            result.append(new_record)
        
        return result


class TypeCaster(BaseTransformer):
    """
    Cast column types.
    
    Usage:
        caster = TypeCaster({
            "price": float,
            "quantity": int,
            "created_at": datetime,
        })
    """
    
    def __init__(
        self,
        type_mapping: dict[str, type],
    ):
        self.type_mapping = type_mapping
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Apply type casting."""
        from datetime import datetime
        
        result = []
        
        for record in records:
            new_record = record.copy()
            
            for column, target_type in self.type_mapping.items():
                if column in new_record and new_record[column] is not None:
                    try:
                        if target_type == datetime:
                            # Handle various datetime formats
                            value = new_record[column]
                            if isinstance(value, str):
                                new_record[column] = datetime.fromisoformat(
                                    value.replace("Z", "+00:00")
                                )
                        else:
                            new_record[column] = target_type(new_record[column])
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"Type casting failed for {column}: {e}"
                        )
            
            result.append(new_record)
        
        return result


class FilterTransformer(BaseTransformer):
    """
    Filter records based on conditions.
    
    Usage:
        filter_tx = FilterTransformer(
            lambda r: r["status"] == "active"
        )
    """
    
    def __init__(
        self,
        predicate: Callable[[dict], bool],
    ):
        self.predicate = predicate
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Filter records using predicate."""
        return [r for r in records if self.predicate(r)]


class DeduplicationTransformer(BaseTransformer):
    """
    Remove duplicate records based on key columns.
    
    Usage:
        dedup = DeduplicationTransformer(
            key_columns=["order_id"],
            keep="last",  # or "first"
        )
    """
    
    def __init__(
        self,
        key_columns: list[str],
        keep: str = "last",
    ):
        self.key_columns = key_columns
        self.keep = keep
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Remove duplicates based on key columns."""
        seen = {}
        
        for record in records:
            key = tuple(record.get(col) for col in self.key_columns)
            
            if self.keep == "first":
                if key not in seen:
                    seen[key] = record
            else:  # keep last
                seen[key] = record
        
        return list(seen.values())


class EnrichmentTransformer(BaseTransformer):
    """
    Enrich records with additional data from lookup sources.
    
    Used for denormalization and adding dimension attributes.
    
    Usage:
        enricher = EnrichmentTransformer(
            lookup_func=get_customer_tier,
            source_key="customer_id",
            target_key="customer_tier",
        )
    """
    
    def __init__(
        self,
        lookup_func: Callable[[Any], Any],
        source_key: str,
        target_key: str,
        default_value: Any = None,
    ):
        self.lookup_func = lookup_func
        self.source_key = source_key
        self.target_key = target_key
        self.default_value = default_value
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Enrich records with lookup values."""
        result = []
        
        for record in records:
            new_record = record.copy()
            
            source_value = record.get(self.source_key)
            if source_value is not None:
                try:
                    lookup_value = self.lookup_func(source_value)
                    new_record[self.target_key] = lookup_value
                except Exception:
                    new_record[self.target_key] = self.default_value
            else:
                new_record[self.target_key] = self.default_value
            
            result.append(new_record)
        
        return result


class AggregationTransformer(BaseTransformer):
    """
    Aggregate records by key columns.
    
    Usage:
        aggregator = AggregationTransformer(
            group_by=["merchant_id", "date"],
            aggregations={
                "revenue": ("order_total", "sum"),
                "order_count": ("order_id", "count"),
                "avg_order_value": ("order_total", "mean"),
            },
        )
    """
    
    def __init__(
        self,
        group_by: list[str],
        aggregations: dict[str, tuple[str, str]],
    ):
        self.group_by = group_by
        self.aggregations = aggregations
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Aggregate records by groups."""
        from collections import defaultdict
        
        # Group records
        groups = defaultdict(list)
        
        for record in records:
            key = tuple(record.get(col) for col in self.group_by)
            groups[key].append(record)
        
        # Compute aggregations
        result = []
        
        for key, group_records in groups.items():
            agg_record = dict(zip(self.group_by, key))
            
            for agg_name, (source_col, agg_func) in self.aggregations.items():
                values = [r.get(source_col) for r in group_records 
                         if r.get(source_col) is not None]
                
                if agg_func == "sum":
                    agg_record[agg_name] = sum(values)
                elif agg_func == "count":
                    agg_record[agg_name] = len(values)
                elif agg_func == "mean":
                    agg_record[agg_name] = sum(values) / len(values) if values else 0
                elif agg_func == "min":
                    agg_record[agg_name] = min(values) if values else None
                elif agg_func == "max":
                    agg_record[agg_name] = max(values) if values else None
            
            result.append(agg_record)
        
        return result


class CustomerTierTransformer(BaseTransformer):
    """
    Calculate customer tier based on LTV.
    
    Tier definitions:
    - Platinum: LTV >= $5000
    - Gold: LTV >= $1000
    - Silver: LTV >= $250
    - Bronze: LTV < $250
    
    Legacy note: Old system used tier1-tier4 numbering.
    tier1 = Platinum, tier4 = Bronze
    """
    
    def __init__(
        self,
        ltv_column: str = "ltv",
        tier_column: str = "tier",
    ):
        self.ltv_column = ltv_column
        self.tier_column = tier_column
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Calculate customer tier from LTV."""
        result = []
        
        for record in records:
            new_record = record.copy()
            ltv = record.get(self.ltv_column, 0) or 0
            
            if ltv >= 5000:
                tier = "platinum"
            elif ltv >= 1000:
                tier = "gold"
            elif ltv >= 250:
                tier = "silver"
            else:
                tier = "bronze"
            
            new_record[self.tier_column] = tier
            result.append(new_record)
        
        return result


class GMVCalculationTransformer(BaseTransformer):
    """
    Calculate GMV (Gross Merchandise Value) from order data.
    
    GMV = sum of order subtotals (before tax and shipping)
    
    This is the key metric for merchant tier calculations.
    """
    
    def __init__(
        self,
        subtotal_column: str = "subtotal",
        gmv_column: str = "gmv",
    ):
        self.subtotal_column = subtotal_column
        self.gmv_column = gmv_column
    
    async def transform(self, records: list[dict]) -> list[dict]:
        """Add GMV column (which equals subtotal for individual orders)."""
        result = []
        
        for record in records:
            new_record = record.copy()
            # For individual orders, GMV = subtotal
            new_record[self.gmv_column] = record.get(self.subtotal_column, 0)
            result.append(new_record)
        
        return result
