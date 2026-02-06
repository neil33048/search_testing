"""
ETL Job: Orders Fact Table

Reads raw order and order item data, applies business logic transformations,
and creates the fact_orders table in the data warehouse.

Input Tables:
    - raw.orders (from PostgreSQL CDC)
    - raw.order_items
    - raw.customers
    - dim.dim_customers

Output Table:
    - marts.fact_orders

Schedule: Hourly via Airflow
Owner: Data Engineering (@data-forge)
"""

from datetime import datetime
from typing import Optional

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DecimalType, 
    IntegerType, TimestampType, BooleanType
)
from pyspark.sql.window import Window

from pipelines.spark.utils.spark_utils import (
    get_spark_session,
    read_from_warehouse,
    write_to_warehouse,
    log_job_metrics,
)
from pipelines.spark.schemas.order_schemas import RAW_ORDERS_SCHEMA, RAW_ORDER_ITEMS_SCHEMA


def extract_orders(spark: SparkSession, run_date: str) -> DataFrame:
    """
    Extract orders from raw layer.
    
    Reads incrementally based on run_date for efficiency.
    Only includes orders that are not cancelled.
    """
    orders_df = read_from_warehouse(
        spark,
        table="raw.orders",
        filter_condition=f"DATE(created_at) = '{run_date}'"
    )
    
    # Filter out cancelled orders for GMV calculation
    # Note: We still keep them in raw for complete audit trail
    orders_df = orders_df.filter(
        ~F.col("status").isin(["cancelled"])
    )
    
    return orders_df


def extract_order_items(spark: SparkSession, order_ids: list) -> DataFrame:
    """Extract order items for given order IDs."""
    order_items_df = read_from_warehouse(spark, table="raw.order_items")
    
    return order_items_df.filter(
        F.col("order_id").isin(order_ids)
    )


def calculate_order_metrics(orders_df: DataFrame, order_items_df: DataFrame) -> DataFrame:
    """
    Calculate order-level metrics from line items.
    
    Metrics:
        - item_count: Total items in order
        - unique_products: Distinct products
        - gmv: Gross Merchandise Value (sum of line subtotals)
        - total_discount: Sum of item-level discounts
        - avg_item_price: Average price per item
    """
    
    # Aggregate order items to order level
    item_metrics = order_items_df.groupBy("order_id").agg(
        F.sum("quantity").alias("item_count"),
        F.countDistinct("product_id").alias("unique_products"),
        F.sum("line_subtotal").alias("items_subtotal"),
        F.sum("discount_amount").alias("items_discount"),
        F.sum("tax_amount").alias("items_tax"),
        F.avg("unit_price").alias("avg_item_price"),
        F.max("unit_price").alias("max_item_price"),
        F.min("unit_price").alias("min_item_price"),
    )
    
    # Join back to orders
    enriched_orders = orders_df.join(
        item_metrics,
        on="order_id",
        how="left"
    )
    
    return enriched_orders


def identify_first_orders(orders_df: DataFrame) -> DataFrame:
    """
    Flag first orders for each customer.
    
    Business Logic:
        - is_first_order = TRUE if this is the customer's earliest order
        - Used for new customer acquisition metrics
        - Important for LTV calculations
    """
    
    # Window to find first order per customer per merchant
    customer_window = Window.partitionBy(
        "merchant_id", "customer_id"
    ).orderBy("created_at")
    
    orders_with_rank = orders_df.withColumn(
        "order_rank",
        F.row_number().over(customer_window)
    )
    
    orders_with_first_flag = orders_with_rank.withColumn(
        "is_first_order",
        F.when(F.col("order_rank") == 1, True).otherwise(False)
    ).drop("order_rank")
    
    return orders_with_first_flag


def calculate_gmv(orders_df: DataFrame) -> DataFrame:
    """
    Calculate GMV (Gross Merchandise Value).
    
    GMV Definition:
        GMV = subtotal (before tax and shipping)
        This is the standard e-commerce GMV calculation.
        
    Note: Some merchants use total_amount as GMV, but our standard
    is subtotal to exclude tax/shipping for cleaner comparisons.
    """
    
    orders_with_gmv = orders_df.withColumn(
        "gmv",
        F.col("subtotal")
    )
    
    # Also calculate net merchandise value (after discounts)
    orders_with_gmv = orders_with_gmv.withColumn(
        "nmv",
        F.col("subtotal") - F.coalesce(F.col("discount_amount"), F.lit(0))
    )
    
    return orders_with_gmv


def enrich_with_customer_tier(
    orders_df: DataFrame, 
    dim_customers_df: DataFrame
) -> DataFrame:
    """
    Add customer tier at time of order.
    
    Customer Tiers (based on LTV):
        - platinum: $5,000+ LTV
        - gold: $1,000 - $5,000 LTV
        - silver: $250 - $1,000 LTV
        - bronze: < $250 LTV
    
    This allows analyzing order patterns by customer tier.
    """
    
    customer_tiers = dim_customers_df.select(
        "customer_id",
        "merchant_id",
        F.col("tier").alias("customer_tier"),
        F.col("ltv").alias("customer_ltv_at_order"),
    )
    
    enriched = orders_df.join(
        customer_tiers,
        on=["customer_id", "merchant_id"],
        how="left"
    )
    
    # Default to bronze for customers without tier
    enriched = enriched.withColumn(
        "customer_tier",
        F.coalesce(F.col("customer_tier"), F.lit("bronze"))
    )
    
    return enriched


def add_time_dimensions(orders_df: DataFrame) -> DataFrame:
    """
    Add time dimension columns for easier aggregation.
    
    Adds:
        - order_date: Date only
        - order_hour: Hour of day (0-23)
        - order_day_of_week: Day of week (1=Monday)
        - order_week: ISO week number
        - order_month: Month (1-12)
        - order_quarter: Quarter (1-4)
        - order_year: Year
        - is_weekend: Boolean
    """
    
    result = orders_df \
        .withColumn("order_date", F.to_date("created_at")) \
        .withColumn("order_hour", F.hour("created_at")) \
        .withColumn("order_day_of_week", F.dayofweek("created_at")) \
        .withColumn("order_week", F.weekofyear("created_at")) \
        .withColumn("order_month", F.month("created_at")) \
        .withColumn("order_quarter", F.quarter("created_at")) \
        .withColumn("order_year", F.year("created_at")) \
        .withColumn(
            "is_weekend", 
            F.col("order_day_of_week").isin([1, 7])  # Sunday=1, Saturday=7
        )
    
    return result


def calculate_order_velocity(orders_df: DataFrame) -> DataFrame:
    """
    Calculate days since customer's previous order.
    
    Used for:
        - Repeat purchase analysis
        - Customer engagement scoring
        - Churn prediction features
    """
    
    customer_window = Window.partitionBy(
        "merchant_id", "customer_id"
    ).orderBy("created_at")
    
    result = orders_df.withColumn(
        "prev_order_at",
        F.lag("created_at").over(customer_window)
    ).withColumn(
        "days_since_prev_order",
        F.datediff(F.col("created_at"), F.col("prev_order_at"))
    ).drop("prev_order_at")
    
    return result


def build_fact_orders(
    spark: SparkSession,
    run_date: str,
    incremental: bool = True
) -> DataFrame:
    """
    Main transformation function to build fact_orders table.
    
    Args:
        spark: SparkSession
        run_date: Date to process (YYYY-MM-DD)
        incremental: If True, only process new data
        
    Returns:
        DataFrame ready to write to fact_orders
    """
    
    print(f"Building fact_orders for {run_date}")
    
    # Extract raw data
    orders_df = extract_orders(spark, run_date)
    
    if orders_df.count() == 0:
        print(f"No orders found for {run_date}")
        return None
    
    order_ids = [row.order_id for row in orders_df.select("order_id").collect()]
    order_items_df = extract_order_items(spark, order_ids)
    
    # Load dimension table
    dim_customers_df = read_from_warehouse(spark, table="marts.dim_customers")
    
    # Apply transformations
    result = orders_df
    result = calculate_order_metrics(result, order_items_df)
    result = identify_first_orders(result)
    result = calculate_gmv(result)
    result = enrich_with_customer_tier(result, dim_customers_df)
    result = add_time_dimensions(result)
    result = calculate_order_velocity(result)
    
    # Select final columns for fact table
    fact_orders = result.select(
        # Keys
        "order_id",
        "merchant_id",
        "customer_id",
        
        # Order details
        "status",
        "channel",
        "order_date",
        "created_at",
        
        # Financials
        "subtotal",
        "discount_amount",
        "tax_amount",
        "shipping_amount",
        "total_amount",
        "gmv",
        "nmv",
        
        # Item metrics
        "item_count",
        "unique_products",
        "avg_item_price",
        
        # Customer context
        "customer_tier",
        "customer_ltv_at_order",
        "is_first_order",
        "days_since_prev_order",
        
        # Time dimensions
        "order_hour",
        "order_day_of_week",
        "order_week",
        "order_month",
        "order_quarter",
        "order_year",
        "is_weekend",
        
        # Attribution
        "utm_source",
        "utm_medium",
        "utm_campaign",
        
        # Metadata
        F.current_timestamp().alias("_loaded_at"),
    )
    
    return fact_orders


def run_job(run_date: Optional[str] = None):
    """Entry point for the ETL job."""
    
    spark = get_spark_session("etl_orders_fact")
    
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        fact_orders = build_fact_orders(spark, run_date)
        
        if fact_orders is not None:
            row_count = fact_orders.count()
            
            # Write to warehouse
            write_to_warehouse(
                df=fact_orders,
                table="marts.fact_orders",
                mode="append",
                partition_cols=["order_date"]
            )
            
            # Log metrics
            log_job_metrics(
                job_name="etl_orders_fact",
                run_date=run_date,
                rows_processed=row_count,
                status="success"
            )
            
            print(f"Successfully wrote {row_count} rows to marts.fact_orders")
        else:
            print("No data to process")
            
    except Exception as e:
        log_job_metrics(
            job_name="etl_orders_fact",
            run_date=run_date,
            rows_processed=0,
            status="failed",
            error=str(e)
        )
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    import sys
    run_date = sys.argv[1] if len(sys.argv) > 1 else None
    run_job(run_date)
