"""
Spark Utilities

Common utilities for PySpark ETL jobs including:
- SparkSession creation
- Data warehouse I/O
- Logging and metrics
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pyspark.sql import SparkSession, DataFrame


def get_spark_session(app_name: str) -> SparkSession:
    """
    Create or get SparkSession with standard configuration.
    
    Configuration includes:
        - Delta Lake support
        - Snowflake connector
        - Adaptive query execution
        - Memory and executor settings
    """
    
    spark = SparkSession.builder \
        .appName(f"meridian_{app_name}") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.sql.shuffle.partitions", "200") \
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
        .getOrCreate()
    
    # Set log level
    spark.sparkContext.setLogLevel("WARN")
    
    return spark


def read_from_warehouse(
    spark: SparkSession,
    table: str,
    filter_condition: Optional[str] = None,
    columns: Optional[List[str]] = None
) -> DataFrame:
    """
    Read data from the data warehouse.
    
    Supports both Snowflake and Delta Lake tables based on configuration.
    
    Args:
        spark: SparkSession
        table: Table name in format "schema.table"
        filter_condition: Optional SQL filter (e.g., "order_date = '2024-01-15'")
        columns: Optional list of columns to select
        
    Returns:
        DataFrame with requested data
    """
    
    # In production, this would read from Snowflake or Delta Lake
    # For local testing, use Parquet files
    
    schema, table_name = table.split(".")
    path = f"s3://meridian-data-warehouse/{schema}/{table_name}"
    
    try:
        df = spark.read.format("delta").load(path)
    except Exception:
        # Fallback to parquet for testing
        df = spark.read.parquet(path)
    
    if filter_condition:
        df = df.filter(filter_condition)
    
    if columns:
        df = df.select(*columns)
    
    return df


def write_to_warehouse(
    df: DataFrame,
    table: str,
    mode: str = "append",
    partition_cols: Optional[List[str]] = None,
    options: Optional[Dict[str, Any]] = None
):
    """
    Write DataFrame to data warehouse.
    
    Args:
        df: DataFrame to write
        table: Target table in format "schema.table"
        mode: Write mode - 'append', 'overwrite', 'merge'
        partition_cols: Columns to partition by
        options: Additional write options
    """
    
    schema, table_name = table.split(".")
    path = f"s3://meridian-data-warehouse/{schema}/{table_name}"
    
    writer = df.write.format("delta").mode(mode)
    
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    
    if options:
        for key, value in options.items():
            writer = writer.option(key, value)
    
    writer.save(path)
    
    print(f"Wrote to {table} with mode={mode}")


def log_job_metrics(
    job_name: str,
    run_date: str,
    rows_processed: int,
    status: str,
    error: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None
):
    """
    Log job metrics to monitoring system.
    
    In production, sends to:
        - DataDog for dashboards
        - Snowflake audit table for lineage
        - Slack for alerts on failure
    """
    
    metric_payload = {
        "job_name": job_name,
        "run_date": run_date,
        "run_timestamp": datetime.now().isoformat(),
        "rows_processed": rows_processed,
        "status": status,
        "error": error,
        **(metrics or {})
    }
    
    print(f"Job Metrics: {metric_payload}")
    
    # In production:
    # - Send to DataDog: datadog_client.gauge('etl.rows_processed', rows_processed, tags=[f'job:{job_name}'])
    # - Insert to audit table
    # - Send Slack alert if status == 'failed'


def get_incremental_filter(
    spark: SparkSession,
    target_table: str,
    timestamp_column: str = "_loaded_at"
) -> Optional[str]:
    """
    Get filter for incremental processing.
    
    Returns filter to get only new records since last successful run.
    """
    
    try:
        target_df = read_from_warehouse(spark, target_table)
        max_timestamp = target_df.agg({timestamp_column: "max"}).collect()[0][0]
        
        if max_timestamp:
            return f"{timestamp_column} > '{max_timestamp}'"
    except Exception:
        pass
    
    return None


def validate_dataframe(
    df: DataFrame,
    required_columns: List[str],
    non_null_columns: Optional[List[str]] = None
) -> bool:
    """
    Validate DataFrame schema and data quality.
    
    Checks:
        - Required columns exist
        - Non-null columns have no nulls
        - DataFrame is not empty
    """
    
    # Check required columns
    df_columns = set(df.columns)
    missing = set(required_columns) - df_columns
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Check for nulls
    if non_null_columns:
        for col in non_null_columns:
            null_count = df.filter(df[col].isNull()).count()
            if null_count > 0:
                raise ValueError(f"Column {col} has {null_count} null values")
    
    # Check not empty
    if df.count() == 0:
        print("Warning: DataFrame is empty")
        return False
    
    return True
