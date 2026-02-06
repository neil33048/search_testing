"""
ETL Job: Customer Dimension Table

Builds the dim_customers dimension table with customer attributes,
lifetime value (LTV), and segmentation data.

Input Tables:
    - raw.customers
    - raw.orders (for LTV calculation)
    - raw.events (for engagement metrics)

Output Table:
    - marts.dim_customers

Schedule: Daily at 03:00 UTC
Owner: Data Engineering (@data-forge)

Business Context:
    - Customer LTV drives tier assignment
    - Tiers affect rate limits and SLA guarantees
    - Segmentation uses RFM (Recency, Frequency, Monetary) model
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


# Customer tier thresholds based on LTV
# These match the merchant tier thresholds but for individual customers
TIER_THRESHOLDS = {
    "platinum": 5000.00,  # $5,000+ LTV
    "gold": 1000.00,      # $1,000 - $5,000 LTV
    "silver": 250.00,     # $250 - $1,000 LTV
    "bronze": 0.00,       # < $250 LTV
}

# Legacy tier mapping (old systems used tier1-tier4)
# tier1 = Platinum (highest), tier4 = Bronze (lowest)
LEGACY_TIER_MAP = {
    "tier1": "platinum",
    "tier2": "gold", 
    "tier3": "silver",
    "tier4": "bronze",
}


def extract_customers(spark: SparkSession) -> DataFrame:
    """Extract raw customer data."""
    return read_from_warehouse(spark, table="raw.customers")


def extract_orders_for_ltv(spark: SparkSession) -> DataFrame:
    """
    Extract orders for LTV calculation.
    
    Only includes completed orders (delivered status).
    Excludes cancelled and refunded orders.
    """
    orders_df = read_from_warehouse(spark, table="raw.orders")
    
    return orders_df.filter(
        F.col("status").isin(["delivered", "shipped", "confirmed", "processing"])
    )


def calculate_customer_ltv(orders_df: DataFrame) -> DataFrame:
    """
    Calculate Lifetime Value (LTV) for each customer.
    
    LTV Definition:
        Sum of all order totals for a customer with a merchant.
        We use total_amount (includes tax/shipping) for LTV,
        different from GMV which uses subtotal.
    
    Also calculates:
        - total_orders: Number of orders
        - avg_order_value: Average order size
        - first_order_at: Date of first purchase
        - last_order_at: Date of most recent purchase
    """
    
    customer_metrics = orders_df.groupBy(
        "merchant_id", "customer_id"
    ).agg(
        # LTV = sum of all order totals
        F.sum("total_amount").alias("ltv"),
        
        # Order count
        F.count("*").alias("total_orders"),
        
        # Average order value
        F.avg("total_amount").alias("avg_order_value"),
        
        # First and last order dates
        F.min("created_at").alias("first_order_at"),
        F.max("created_at").alias("last_order_at"),
        
        # Total items purchased
        F.sum("item_count").alias("total_items_purchased"),
        
        # Spending patterns
        F.max("total_amount").alias("largest_order"),
        F.min("total_amount").alias("smallest_order"),
        F.stddev("total_amount").alias("order_value_stddev"),
    )
    
    return customer_metrics


def assign_customer_tier(df: DataFrame) -> DataFrame:
    """
    Assign customer tier based on LTV.
    
    Tier Thresholds:
        - platinum: $5,000+ LTV
        - gold: $1,000 - $5,000 LTV
        - silver: $250 - $1,000 LTV
        - bronze: < $250 LTV
    
    Note: Legacy systems used tier1-tier4 numbering.
    tier1 = Platinum, tier4 = Bronze
    """
    
    result = df.withColumn(
        "tier",
        F.when(F.col("ltv") >= TIER_THRESHOLDS["platinum"], "platinum")
         .when(F.col("ltv") >= TIER_THRESHOLDS["gold"], "gold")
         .when(F.col("ltv") >= TIER_THRESHOLDS["silver"], "silver")
         .otherwise("bronze")
    )
    
    # Add legacy tier for backwards compatibility with old reports
    result = result.withColumn(
        "legacy_tier",
        F.when(F.col("tier") == "platinum", "tier1")
         .when(F.col("tier") == "gold", "tier2")
         .when(F.col("tier") == "silver", "tier3")
         .otherwise("tier4")
    )
    
    return result


def calculate_rfm_scores(df: DataFrame, reference_date: str) -> DataFrame:
    """
    Calculate RFM (Recency, Frequency, Monetary) scores.
    
    RFM Model:
        - Recency: Days since last order (lower is better)
        - Frequency: Number of orders (higher is better)
        - Monetary: Total spend / LTV (higher is better)
    
    Each dimension scored 1-5 (5 is best).
    Combined RFM score used for segmentation.
    """
    
    ref_date = F.to_date(F.lit(reference_date))
    
    # Calculate recency in days
    result = df.withColumn(
        "days_since_last_order",
        F.datediff(ref_date, F.col("last_order_at"))
    )
    
    # Recency score (lower days = higher score)
    result = result.withColumn(
        "recency_score",
        F.when(F.col("days_since_last_order") <= 7, 5)
         .when(F.col("days_since_last_order") <= 30, 4)
         .when(F.col("days_since_last_order") <= 90, 3)
         .when(F.col("days_since_last_order") <= 180, 2)
         .otherwise(1)
    )
    
    # Frequency score (more orders = higher score)
    result = result.withColumn(
        "frequency_score",
        F.when(F.col("total_orders") >= 10, 5)
         .when(F.col("total_orders") >= 5, 4)
         .when(F.col("total_orders") >= 3, 3)
         .when(F.col("total_orders") >= 2, 2)
         .otherwise(1)
    )
    
    # Monetary score (higher LTV = higher score)
    result = result.withColumn(
        "monetary_score",
        F.when(F.col("ltv") >= 1000, 5)
         .when(F.col("ltv") >= 500, 4)
         .when(F.col("ltv") >= 200, 3)
         .when(F.col("ltv") >= 50, 2)
         .otherwise(1)
    )
    
    # Combined RFM score
    result = result.withColumn(
        "rfm_score",
        F.col("recency_score") + F.col("frequency_score") + F.col("monetary_score")
    )
    
    return result


def assign_customer_segment(df: DataFrame) -> DataFrame:
    """
    Assign customer segment based on RFM scores.
    
    Segments:
        - champion: High in all dimensions (R>=4, F>=4, M>=4)
        - loyal: High frequency, moderate recency (F>=4, R>=3)
        - promising: Recent but low frequency (R>=4, F<=2)
        - at_risk: Were loyal but haven't purchased recently (R<=2, F>=3)
        - hibernating: Low recency and frequency (R<=2, F<=2)
        - needs_attention: Moderate across all (R=3, F=3)
        - regular: Default
    
    Used for targeted marketing campaigns.
    """
    
    result = df.withColumn(
        "segment",
        F.when(
            (F.col("recency_score") >= 4) & 
            (F.col("frequency_score") >= 4) & 
            (F.col("monetary_score") >= 4),
            "champion"
        ).when(
            (F.col("frequency_score") >= 4) & (F.col("recency_score") >= 3),
            "loyal"
        ).when(
            (F.col("recency_score") >= 4) & (F.col("frequency_score") <= 2),
            "promising"
        ).when(
            (F.col("recency_score") <= 2) & (F.col("frequency_score") >= 3),
            "at_risk"
        ).when(
            (F.col("recency_score") <= 2) & (F.col("frequency_score") <= 2),
            "hibernating"
        ).when(
            (F.col("recency_score") == 3) & (F.col("frequency_score") == 3),
            "needs_attention"
        ).otherwise("regular")
    )
    
    return result


def calculate_churn_risk(df: DataFrame) -> DataFrame:
    """
    Calculate churn risk score (0.0 - 1.0).
    
    Churn Risk Logic:
        - >365 days since last order: 95% risk
        - >180 days: 75% risk
        - >90 days: 50% risk
        - >30 days: 25% risk
        - <=30 days: 10% risk
    
    Used for proactive retention campaigns.
    """
    
    result = df.withColumn(
        "churn_risk",
        F.when(F.col("days_since_last_order") > 365, 0.95)
         .when(F.col("days_since_last_order") > 180, 0.75)
         .when(F.col("days_since_last_order") > 90, 0.50)
         .when(F.col("days_since_last_order") > 30, 0.25)
         .otherwise(0.10)
    )
    
    return result


def calculate_customer_tenure(df: DataFrame, reference_date: str) -> DataFrame:
    """
    Calculate customer tenure and lifecycle stage.
    
    Tenure = months since first order
    
    Lifecycle Stages:
        - new: 0-3 months
        - developing: 3-12 months
        - established: 12-24 months
        - mature: 24+ months
    """
    
    ref_date = F.to_date(F.lit(reference_date))
    
    result = df.withColumn(
        "tenure_months",
        F.months_between(ref_date, F.col("first_order_at"))
    )
    
    result = result.withColumn(
        "lifecycle_stage",
        F.when(F.col("tenure_months") < 3, "new")
         .when(F.col("tenure_months") < 12, "developing")
         .when(F.col("tenure_months") < 24, "established")
         .otherwise("mature")
    )
    
    return result


def build_dim_customers(
    spark: SparkSession,
    run_date: str
) -> DataFrame:
    """
    Main transformation function to build dim_customers table.
    
    This is a Type 1 SCD (Slowly Changing Dimension) - we overwrite
    with current state. Historical tier changes are not preserved.
    """
    
    print(f"Building dim_customers for {run_date}")
    
    # Extract data
    customers_df = extract_customers(spark)
    orders_df = extract_orders_for_ltv(spark)
    
    # Calculate LTV and order metrics
    customer_metrics = calculate_customer_ltv(orders_df)
    
    # Join customer attributes with metrics
    result = customers_df.join(
        customer_metrics,
        on=["merchant_id", "customer_id"],
        how="left"
    )
    
    # Fill nulls for customers with no orders
    result = result.fillna({
        "ltv": 0.0,
        "total_orders": 0,
        "avg_order_value": 0.0,
        "total_items_purchased": 0,
    })
    
    # Apply business logic transformations
    result = assign_customer_tier(result)
    result = calculate_rfm_scores(result, run_date)
    result = assign_customer_segment(result)
    result = calculate_churn_risk(result)
    result = calculate_customer_tenure(result, run_date)
    
    # Calculate derived metrics
    result = result.withColumn(
        "is_repeat_customer",
        F.col("total_orders") > 1
    )
    
    result = result.withColumn(
        "has_recent_activity",
        F.col("days_since_last_order") <= 30
    )
    
    # Select final columns
    dim_customers = result.select(
        # Keys
        "customer_id",
        "merchant_id",
        
        # Profile
        "email",
        "first_name",
        "last_name",
        "status",
        
        # Tier and segmentation
        "tier",
        "legacy_tier",  # For old reports
        "segment",
        "lifecycle_stage",
        
        # Value metrics
        "ltv",
        "total_orders",
        "avg_order_value",
        "total_items_purchased",
        "largest_order",
        "smallest_order",
        
        # Time metrics
        "first_order_at",
        "last_order_at",
        "days_since_last_order",
        "tenure_months",
        
        # RFM scores
        "recency_score",
        "frequency_score",
        "monetary_score",
        "rfm_score",
        
        # Risk and flags
        "churn_risk",
        "is_repeat_customer",
        "has_recent_activity",
        
        # Marketing preferences
        "email_opt_in",
        "sms_opt_in",
        "acquisition_source",
        
        # Timestamps
        "created_at",
        F.current_timestamp().alias("_loaded_at"),
    )
    
    return dim_customers


def run_job(run_date: Optional[str] = None):
    """Entry point for the ETL job."""
    
    spark = get_spark_session("etl_customer_dim")
    
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        dim_customers = build_dim_customers(spark, run_date)
        row_count = dim_customers.count()
        
        # Full refresh - overwrite entire table
        write_to_warehouse(
            df=dim_customers,
            table="marts.dim_customers",
            mode="overwrite",
            partition_cols=["merchant_id"]
        )
        
        log_job_metrics(
            job_name="etl_customer_dim",
            run_date=run_date,
            rows_processed=row_count,
            status="success"
        )
        
        print(f"Successfully wrote {row_count} rows to marts.dim_customers")
        
    except Exception as e:
        log_job_metrics(
            job_name="etl_customer_dim",
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
