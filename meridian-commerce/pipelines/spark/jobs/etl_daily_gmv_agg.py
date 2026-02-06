"""
ETL Job: Daily GMV Aggregation

Aggregates daily GMV (Gross Merchandise Value) and key business metrics 
at merchant level. Powers the Pulse dashboard and merchant tier calculations.

Input Tables:
    - marts.fact_orders
    - marts.dim_customers

Output Table:
    - marts.agg_daily_gmv

Schedule: Daily at 04:00 UTC (after fact_orders completes)
Owner: Data Engineering (@data-forge)

Key Metrics:
    - GMV: Gross Merchandise Value (sum of order subtotals)
    - NMV: Net Merchandise Value (after discounts)
    - AOV: Average Order Value
    - Order Count
    - Customer metrics (new vs returning)
"""

from datetime import datetime, timedelta
from typing import Optional, List

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from pipelines.spark.utils.spark_utils import (
    get_spark_session,
    read_from_warehouse,
    write_to_warehouse,
    log_job_metrics,
)


def extract_daily_orders(
    spark: SparkSession, 
    start_date: str, 
    end_date: str
) -> DataFrame:
    """
    Extract orders for the date range.
    
    Filters:
        - Excludes cancelled orders (no GMV contribution)
        - Excludes refunded orders (GMV already counted, handled separately)
    """
    
    fact_orders = read_from_warehouse(spark, table="marts.fact_orders")
    
    return fact_orders.filter(
        (F.col("order_date") >= start_date) &
        (F.col("order_date") <= end_date) &
        (~F.col("status").isin(["cancelled", "refunded"]))
    )


def calculate_daily_gmv(orders_df: DataFrame) -> DataFrame:
    """
    Calculate daily GMV aggregates by merchant.
    
    GMV vs Revenue:
        - GMV = subtotal (product value, used for tier calculation)
        - Revenue = total_amount (includes tax/shipping)
        
    We use GMV for merchant tier thresholds per company policy.
    """
    
    daily_agg = orders_df.groupBy(
        "merchant_id",
        "order_date"
    ).agg(
        # Core GMV metrics
        F.sum("gmv").alias("total_gmv"),
        F.sum("nmv").alias("total_nmv"),
        F.sum("total_amount").alias("total_revenue"),
        
        # Order metrics
        F.count("*").alias("order_count"),
        F.sum("item_count").alias("total_items_sold"),
        F.sum("unique_products").alias("total_unique_products"),
        
        # Average order value
        F.avg("gmv").alias("avg_order_value"),
        F.avg("total_amount").alias("avg_revenue_per_order"),
        
        # Discounts
        F.sum("discount_amount").alias("total_discounts"),
        
        # Customer metrics
        F.countDistinct("customer_id").alias("unique_customers"),
        F.sum(F.when(F.col("is_first_order"), 1).otherwise(0)).alias("new_customers"),
        
        # Order distribution
        F.max("gmv").alias("max_order_gmv"),
        F.min("gmv").alias("min_order_gmv"),
        F.percentile_approx("gmv", 0.5).alias("median_order_gmv"),
    )
    
    # Calculate derived metrics
    daily_agg = daily_agg.withColumn(
        "returning_customers",
        F.col("unique_customers") - F.col("new_customers")
    )
    
    daily_agg = daily_agg.withColumn(
        "new_customer_rate",
        F.when(
            F.col("unique_customers") > 0,
            F.col("new_customers") / F.col("unique_customers")
        ).otherwise(0.0)
    )
    
    daily_agg = daily_agg.withColumn(
        "discount_rate",
        F.when(
            F.col("total_gmv") > 0,
            F.col("total_discounts") / F.col("total_gmv")
        ).otherwise(0.0)
    )
    
    daily_agg = daily_agg.withColumn(
        "items_per_order",
        F.when(
            F.col("order_count") > 0,
            F.col("total_items_sold") / F.col("order_count")
        ).otherwise(0.0)
    )
    
    return daily_agg


def add_channel_breakdown(orders_df: DataFrame) -> DataFrame:
    """
    Calculate GMV breakdown by channel.
    
    Channels:
        - web: Desktop browser
        - mobile_web: Mobile browser
        - ios_app: iOS native app
        - android_app: Android native app
        - api: Direct API integration
    """
    
    channel_breakdown = orders_df.groupBy(
        "merchant_id",
        "order_date"
    ).pivot("channel").agg(
        F.sum("gmv").alias("gmv"),
        F.count("*").alias("orders")
    )
    
    return channel_breakdown


def add_tier_breakdown(orders_df: DataFrame) -> DataFrame:
    """
    Calculate GMV breakdown by customer tier.
    
    Customer Tiers:
        - platinum: $5,000+ LTV
        - gold: $1,000-$5,000 LTV
        - silver: $250-$1,000 LTV
        - bronze: <$250 LTV
        
    Useful for understanding revenue concentration by customer value.
    """
    
    tier_breakdown = orders_df.groupBy(
        "merchant_id",
        "order_date"
    ).pivot("customer_tier", ["platinum", "gold", "silver", "bronze"]).agg(
        F.sum("gmv").alias("gmv"),
        F.count("*").alias("orders"),
        F.countDistinct("customer_id").alias("customers")
    )
    
    return tier_breakdown


def calculate_period_over_period(
    daily_agg: DataFrame, 
    orders_df: DataFrame
) -> DataFrame:
    """
    Calculate period-over-period comparisons.
    
    Compares each day to:
        - Previous day (DoD)
        - Same day last week (WoW)
        - Same day last month (MoM)
    """
    
    window_prev_day = Window.partitionBy("merchant_id").orderBy("order_date")
    
    result = daily_agg.withColumn(
        "prev_day_gmv",
        F.lag("total_gmv", 1).over(window_prev_day)
    ).withColumn(
        "prev_week_gmv",
        F.lag("total_gmv", 7).over(window_prev_day)
    )
    
    # Calculate change percentages
    result = result.withColumn(
        "gmv_dod_change",
        F.when(
            F.col("prev_day_gmv") > 0,
            (F.col("total_gmv") - F.col("prev_day_gmv")) / F.col("prev_day_gmv") * 100
        ).otherwise(None)
    )
    
    result = result.withColumn(
        "gmv_wow_change",
        F.when(
            F.col("prev_week_gmv") > 0,
            (F.col("total_gmv") - F.col("prev_week_gmv")) / F.col("prev_week_gmv") * 100
        ).otherwise(None)
    )
    
    return result


def calculate_rolling_metrics(daily_agg: DataFrame) -> DataFrame:
    """
    Calculate rolling window metrics.
    
    Rolling Windows:
        - 7-day rolling GMV and order count
        - 30-day rolling GMV and order count
        - MTD (month to date) totals
        - QTD (quarter to date) totals
    """
    
    window_7d = Window.partitionBy("merchant_id").orderBy("order_date").rowsBetween(-6, 0)
    window_30d = Window.partitionBy("merchant_id").orderBy("order_date").rowsBetween(-29, 0)
    
    result = daily_agg \
        .withColumn("gmv_7d_rolling", F.sum("total_gmv").over(window_7d)) \
        .withColumn("orders_7d_rolling", F.sum("order_count").over(window_7d)) \
        .withColumn("gmv_30d_rolling", F.sum("total_gmv").over(window_30d)) \
        .withColumn("orders_30d_rolling", F.sum("order_count").over(window_30d)) \
        .withColumn("avg_daily_gmv_7d", F.avg("total_gmv").over(window_7d)) \
        .withColumn("avg_daily_gmv_30d", F.avg("total_gmv").over(window_30d))
    
    return result


def build_daily_gmv_agg(
    spark: SparkSession,
    start_date: str,
    end_date: str
) -> DataFrame:
    """
    Main transformation function to build agg_daily_gmv table.
    
    Args:
        spark: SparkSession
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        DataFrame ready to write to agg_daily_gmv
    """
    
    print(f"Building agg_daily_gmv for {start_date} to {end_date}")
    
    # Extract orders
    orders_df = extract_daily_orders(spark, start_date, end_date)
    
    if orders_df.count() == 0:
        print("No orders found for date range")
        return None
    
    # Calculate core GMV aggregates
    daily_agg = calculate_daily_gmv(orders_df)
    
    # Add channel and tier breakdowns
    channel_breakdown = add_channel_breakdown(orders_df)
    tier_breakdown = add_tier_breakdown(orders_df)
    
    # Join breakdowns
    daily_agg = daily_agg.join(
        channel_breakdown,
        on=["merchant_id", "order_date"],
        how="left"
    )
    
    daily_agg = daily_agg.join(
        tier_breakdown,
        on=["merchant_id", "order_date"],
        how="left"
    )
    
    # Calculate period comparisons and rolling metrics
    daily_agg = calculate_period_over_period(daily_agg, orders_df)
    daily_agg = calculate_rolling_metrics(daily_agg)
    
    # Add metadata
    daily_agg = daily_agg.withColumn(
        "_loaded_at",
        F.current_timestamp()
    )
    
    return daily_agg


def update_merchant_tier(spark: SparkSession):
    """
    Update merchant tier based on trailing 12-month GMV.
    
    Tier Thresholds (Annual GMV):
        - Platinum: > $2,000,000
        - Gold: $500,000 - $2,000,000
        - Silver: $100,000 - $500,000
        - Bronze: < $100,000
        
    This affects rate limits and SLA guarantees.
    """
    
    # Calculate trailing 12-month GMV per merchant
    agg_daily_gmv = read_from_warehouse(spark, table="marts.agg_daily_gmv")
    
    twelve_months_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    merchant_gmv = agg_daily_gmv.filter(
        F.col("order_date") >= twelve_months_ago
    ).groupBy("merchant_id").agg(
        F.sum("total_gmv").alias("gmv_12m")
    )
    
    # Assign tiers
    merchant_tiers = merchant_gmv.withColumn(
        "calculated_tier",
        F.when(F.col("gmv_12m") >= 2000000, "platinum")
         .when(F.col("gmv_12m") >= 500000, "gold")
         .when(F.col("gmv_12m") >= 100000, "silver")
         .otherwise("bronze")
    )
    
    # Would update merchants table here
    print("Merchant tier calculation complete")
    
    return merchant_tiers


def run_job(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Entry point for the ETL job."""
    
    spark = get_spark_session("etl_daily_gmv_agg")
    
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = start_date
    
    try:
        agg_daily_gmv = build_daily_gmv_agg(spark, start_date, end_date)
        
        if agg_daily_gmv is not None:
            row_count = agg_daily_gmv.count()
            
            # Write with partition overwrite for date range
            write_to_warehouse(
                df=agg_daily_gmv,
                table="marts.agg_daily_gmv",
                mode="overwrite",  # Partition overwrite
                partition_cols=["order_date"]
            )
            
            # Update merchant tiers after GMV aggregation
            update_merchant_tier(spark)
            
            log_job_metrics(
                job_name="etl_daily_gmv_agg",
                run_date=start_date,
                rows_processed=row_count,
                status="success"
            )
            
            print(f"Successfully wrote {row_count} rows to marts.agg_daily_gmv")
        else:
            print("No data to process")
            
    except Exception as e:
        log_job_metrics(
            job_name="etl_daily_gmv_agg",
            run_date=start_date,
            rows_processed=0,
            status="failed",
            error=str(e)
        )
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    import sys
    start_date = sys.argv[1] if len(sys.argv) > 1 else None
    end_date = sys.argv[2] if len(sys.argv) > 2 else start_date
    run_job(start_date, end_date)
