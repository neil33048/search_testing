"""
ETL Job: Product Analytics

Calculates product-level analytics for merchant dashboards and
Catalyst recommendation features.

Input Tables:
    - marts.fact_orders
    - raw.order_items
    - raw.products
    - raw.events (Beacon)

Output Table:
    - marts.agg_product_performance

Schedule: Daily at 05:00 UTC
Owner: Analytics Team

Key Metrics:
    - Sales metrics (revenue, units sold, order count)
    - Conversion metrics (view-to-cart, cart-to-purchase)
    - Inventory metrics (days of stock, stockout risk)
"""

from datetime import datetime, timedelta
from typing import Optional

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from pipelines.spark.utils.spark_utils import (
    get_spark_session,
    read_from_warehouse,
    write_to_warehouse,
    log_job_metrics,
)


def extract_order_items(spark: SparkSession, lookback_days: int = 30) -> DataFrame:
    """Extract order items for lookback period."""
    
    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    order_items = read_from_warehouse(spark, table="raw.order_items")
    
    return order_items.filter(F.col("created_at") >= cutoff_date)


def extract_product_events(spark: SparkSession, lookback_days: int = 30) -> DataFrame:
    """
    Extract product-related events from Beacon.
    
    Event Types:
        - product_view: Product detail page view
        - add_to_cart: Added to cart
        - remove_from_cart: Removed from cart
        - checkout_started: Product in checkout
        - order_completed: Product purchased
    """
    
    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    events = read_from_warehouse(spark, table="raw.events")
    
    product_events = events.filter(
        (F.col("created_at") >= cutoff_date) &
        (F.col("event_type").isin([
            "product_view",
            "add_to_cart",
            "remove_from_cart",
            "checkout_started",
            "order_completed"
        ]))
    )
    
    # Extract product_id from event properties
    product_events = product_events.withColumn(
        "product_id",
        F.get_json_object(F.col("properties"), "$.product_id")
    )
    
    return product_events


def calculate_sales_metrics(order_items_df: DataFrame) -> DataFrame:
    """
    Calculate sales metrics per product.
    
    Metrics:
        - total_revenue: Sum of line item totals
        - total_units_sold: Sum of quantities
        - order_count: Number of orders containing this product
        - avg_selling_price: Average price sold at
        - avg_quantity_per_order: Average units per order
    """
    
    sales_metrics = order_items_df.groupBy(
        "merchant_id",
        "product_id"
    ).agg(
        F.sum("total_amount").alias("total_revenue"),
        F.sum("quantity").alias("total_units_sold"),
        F.countDistinct("order_id").alias("order_count"),
        F.avg("unit_price").alias("avg_selling_price"),
        F.avg("quantity").alias("avg_quantity_per_order"),
        F.sum("discount_amount").alias("total_discounts"),
        F.max("created_at").alias("last_sold_at"),
    )
    
    return sales_metrics


def calculate_funnel_metrics(events_df: DataFrame) -> DataFrame:
    """
    Calculate product conversion funnel metrics.
    
    Funnel Stages:
        product_view -> add_to_cart -> checkout_started -> order_completed
    
    Conversion Rates:
        - view_to_cart_rate: add_to_cart / product_view
        - cart_to_checkout_rate: checkout_started / add_to_cart
        - checkout_to_purchase_rate: order_completed / checkout_started
        - overall_conversion_rate: order_completed / product_view
    """
    
    # Pivot event counts by type
    funnel_counts = events_df.groupBy(
        "merchant_id",
        "product_id"
    ).pivot(
        "event_type",
        ["product_view", "add_to_cart", "checkout_started", "order_completed"]
    ).agg(F.count("*"))
    
    # Rename columns for clarity
    funnel_counts = funnel_counts \
        .withColumnRenamed("product_view", "view_count") \
        .withColumnRenamed("add_to_cart", "cart_add_count") \
        .withColumnRenamed("checkout_started", "checkout_count") \
        .withColumnRenamed("order_completed", "purchase_count")
    
    # Fill nulls with 0
    funnel_counts = funnel_counts.fillna(0)
    
    # Calculate conversion rates
    funnel_metrics = funnel_counts \
        .withColumn(
            "view_to_cart_rate",
            F.when(F.col("view_count") > 0, 
                   F.col("cart_add_count") / F.col("view_count"))
            .otherwise(0.0)
        ) \
        .withColumn(
            "cart_to_checkout_rate",
            F.when(F.col("cart_add_count") > 0,
                   F.col("checkout_count") / F.col("cart_add_count"))
            .otherwise(0.0)
        ) \
        .withColumn(
            "checkout_to_purchase_rate",
            F.when(F.col("checkout_count") > 0,
                   F.col("purchase_count") / F.col("checkout_count"))
            .otherwise(0.0)
        ) \
        .withColumn(
            "overall_conversion_rate",
            F.when(F.col("view_count") > 0,
                   F.col("purchase_count") / F.col("view_count"))
            .otherwise(0.0)
        )
    
    return funnel_metrics


def calculate_inventory_metrics(
    sales_metrics: DataFrame,
    products_df: DataFrame
) -> DataFrame:
    """
    Calculate inventory and stock metrics.
    
    Metrics:
        - days_of_stock: Current inventory / avg daily sales
        - stockout_risk: Low if >30 days, Medium if 10-30, High if <10
        - reorder_point: When to reorder based on velocity
    """
    
    # Calculate average daily sales (assuming 30-day window)
    sales_with_velocity = sales_metrics.withColumn(
        "avg_daily_units",
        F.col("total_units_sold") / 30.0
    )
    
    # Join with product inventory
    inventory_data = products_df.select(
        "product_id",
        "merchant_id",
        "inventory_quantity",
        "low_stock_threshold",
        "cost",
        "price"
    )
    
    result = sales_with_velocity.join(
        inventory_data,
        on=["merchant_id", "product_id"],
        how="left"
    )
    
    # Calculate days of stock
    result = result.withColumn(
        "days_of_stock",
        F.when(
            F.col("avg_daily_units") > 0,
            F.col("inventory_quantity") / F.col("avg_daily_units")
        ).otherwise(999)  # High number if no sales
    )
    
    # Stockout risk classification
    result = result.withColumn(
        "stockout_risk",
        F.when(F.col("days_of_stock") < 7, "critical")
         .when(F.col("days_of_stock") < 14, "high")
         .when(F.col("days_of_stock") < 30, "medium")
         .otherwise("low")
    )
    
    # Calculate margin
    result = result.withColumn(
        "margin",
        F.when(
            F.col("price") > 0,
            (F.col("price") - F.coalesce(F.col("cost"), F.lit(0))) / F.col("price")
        ).otherwise(0.0)
    )
    
    return result


def calculate_product_ranking(df: DataFrame) -> DataFrame:
    """
    Calculate product rankings within merchant.
    
    Rankings:
        - revenue_rank: By total revenue (1 = top seller)
        - units_rank: By units sold
        - conversion_rank: By conversion rate
        - velocity_rank: By sales velocity
    """
    
    window = Window.partitionBy("merchant_id")
    
    result = df \
        .withColumn(
            "revenue_rank",
            F.dense_rank().over(window.orderBy(F.desc("total_revenue")))
        ) \
        .withColumn(
            "units_rank",
            F.dense_rank().over(window.orderBy(F.desc("total_units_sold")))
        ) \
        .withColumn(
            "conversion_rank",
            F.dense_rank().over(window.orderBy(F.desc("overall_conversion_rate")))
        ) \
        .withColumn(
            "velocity_rank",
            F.dense_rank().over(window.orderBy(F.desc("avg_daily_units")))
        )
    
    # Create performance tier based on revenue rank
    result = result.withColumn(
        "performance_tier",
        F.when(F.col("revenue_rank") <= 10, "top_10")
         .when(F.col("revenue_rank") <= 50, "top_50")
         .when(F.col("revenue_rank") <= 100, "top_100")
         .otherwise("long_tail")
    )
    
    return result


def build_product_analytics(
    spark: SparkSession,
    lookback_days: int = 30
) -> DataFrame:
    """
    Main transformation function to build agg_product_performance table.
    """
    
    print(f"Building agg_product_performance for last {lookback_days} days")
    
    # Extract data
    order_items_df = extract_order_items(spark, lookback_days)
    events_df = extract_product_events(spark, lookback_days)
    products_df = read_from_warehouse(spark, table="raw.products")
    
    # Calculate metrics
    sales_metrics = calculate_sales_metrics(order_items_df)
    funnel_metrics = calculate_funnel_metrics(events_df)
    
    # Join sales and funnel metrics
    combined = sales_metrics.join(
        funnel_metrics,
        on=["merchant_id", "product_id"],
        how="outer"
    )
    
    # Add inventory metrics
    combined = calculate_inventory_metrics(combined, products_df)
    
    # Add product attributes
    product_attrs = products_df.select(
        "product_id",
        "merchant_id",
        "name",
        "sku",
        "category_path",
        "product_type",
        "status"
    )
    
    combined = combined.join(
        product_attrs,
        on=["merchant_id", "product_id"],
        how="left"
    )
    
    # Calculate rankings
    result = calculate_product_ranking(combined)
    
    # Add metadata
    result = result.withColumn("_loaded_at", F.current_timestamp())
    result = result.withColumn("lookback_days", F.lit(lookback_days))
    
    return result


def run_job(lookback_days: int = 30):
    """Entry point for the ETL job."""
    
    spark = get_spark_session("etl_product_analytics")
    
    try:
        agg_product_performance = build_product_analytics(spark, lookback_days)
        row_count = agg_product_performance.count()
        
        write_to_warehouse(
            df=agg_product_performance,
            table="marts.agg_product_performance",
            mode="overwrite"
        )
        
        log_job_metrics(
            job_name="etl_product_analytics",
            run_date=datetime.now().strftime("%Y-%m-%d"),
            rows_processed=row_count,
            status="success"
        )
        
        print(f"Successfully wrote {row_count} rows to marts.agg_product_performance")
        
    except Exception as e:
        log_job_metrics(
            job_name="etl_product_analytics",
            run_date=datetime.now().strftime("%Y-%m-%d"),
            rows_processed=0,
            status="failed",
            error=str(e)
        )
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    import sys
    lookback_days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run_job(lookback_days)
