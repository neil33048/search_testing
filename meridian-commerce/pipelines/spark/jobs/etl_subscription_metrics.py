"""
ETL Job: Subscription Metrics

Calculates subscription/recurring revenue metrics for merchants
with subscribe-and-save programs.

Input Tables:
    - raw.subscriptions
    - raw.orders (for subscription orders)
    - raw.customers

Output Table:
    - marts.agg_subscription_metrics

Schedule: Daily at 06:00 UTC
Owner: Subscriptions Team

Key Metrics:
    - MRR (Monthly Recurring Revenue)
    - ARR (Annual Recurring Revenue)
    - Churn rate (subscription cancellations)
    - LTV for subscribers vs non-subscribers
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


# Subscription frequency to monthly multiplier
# Used to normalize all subscriptions to monthly revenue
FREQUENCY_MULTIPLIER = {
    "weekly": 4.33,      # ~4.33 weeks per month
    "biweekly": 2.17,    # ~2.17 bi-weeks per month
    "monthly": 1.0,
    "bimonthly": 0.5,    # Every 2 months
    "quarterly": 0.33,   # Every 3 months
    "annually": 0.083,   # Once per year
}


def extract_subscriptions(spark: SparkSession) -> DataFrame:
    """Extract subscription data."""
    return read_from_warehouse(spark, table="raw.subscriptions")


def calculate_mrr(subscriptions_df: DataFrame) -> DataFrame:
    """
    Calculate Monthly Recurring Revenue (MRR).
    
    MRR Calculation:
        For each subscription, normalize to monthly value based on frequency.
        Example: $50 weekly subscription = $50 * 4.33 = $216.50 MRR
    
    Only active subscriptions count toward MRR.
    """
    
    # Only count active subscriptions
    active_subs = subscriptions_df.filter(F.col("status") == "active")
    
    # Map frequency to multiplier
    frequency_mapping = F.create_map([
        F.lit(k) if i % 2 == 0 else F.lit(v)
        for i, (k, v) in enumerate(
            [(k, v) for k, v in FREQUENCY_MULTIPLIER.items() for _ in range(2)]
        )
    ])
    
    # Calculate monthly value for each subscription
    subs_with_mrr = active_subs.withColumn(
        "monthly_multiplier",
        F.when(F.col("frequency") == "weekly", 4.33)
         .when(F.col("frequency") == "biweekly", 2.17)
         .when(F.col("frequency") == "monthly", 1.0)
         .when(F.col("frequency") == "bimonthly", 0.5)
         .when(F.col("frequency") == "quarterly", 0.33)
         .when(F.col("frequency") == "annually", 0.083)
         .otherwise(1.0)
    )
    
    subs_with_mrr = subs_with_mrr.withColumn(
        "subscription_mrr",
        F.col("estimated_total") * F.col("monthly_multiplier")
    )
    
    return subs_with_mrr


def aggregate_merchant_mrr(subs_with_mrr: DataFrame) -> DataFrame:
    """
    Aggregate MRR at merchant level.
    
    Metrics:
        - total_mrr: Sum of all subscription MRR
        - arr: Annual Recurring Revenue (MRR * 12)
        - active_subscriptions: Count of active subscriptions
        - avg_subscription_value: Average monthly value per subscription
    """
    
    merchant_mrr = subs_with_mrr.groupBy("merchant_id").agg(
        F.sum("subscription_mrr").alias("total_mrr"),
        F.count("*").alias("active_subscriptions"),
        F.avg("subscription_mrr").alias("avg_subscription_mrr"),
        F.countDistinct("customer_id").alias("unique_subscribers"),
    )
    
    # Calculate ARR
    merchant_mrr = merchant_mrr.withColumn(
        "total_arr",
        F.col("total_mrr") * 12
    )
    
    return merchant_mrr


def calculate_churn_metrics(
    subscriptions_df: DataFrame,
    lookback_days: int = 30
) -> DataFrame:
    """
    Calculate subscription churn metrics.
    
    Churn Rate:
        Subscriptions cancelled in period / Active subscriptions at period start
    
    Churn Reasons (for analysis):
        - price: Too expensive
        - not_using: Not using product
        - competitor: Switched to competitor
        - temporary: Temporary pause turned permanent
        - other: Various other reasons
    """
    
    cutoff_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    # Count cancellations in period
    cancellations = subscriptions_df.filter(
        (F.col("status") == "cancelled") &
        (F.col("cancelled_at") >= cutoff_date)
    )
    
    churn_by_merchant = cancellations.groupBy("merchant_id").agg(
        F.count("*").alias("churned_subscriptions"),
        F.sum("subscription_mrr").alias("churned_mrr")
    )
    
    # Churn by reason (for product insights)
    churn_by_reason = cancellations.groupBy(
        "merchant_id",
        "cancellation_reason"
    ).agg(
        F.count("*").alias("count")
    ).groupBy("merchant_id").pivot(
        "cancellation_reason"
    ).agg(F.first("count"))
    
    return churn_by_merchant.join(churn_by_reason, on="merchant_id", how="left")


def calculate_subscriber_ltv(
    subscriptions_df: DataFrame,
    orders_df: DataFrame
) -> DataFrame:
    """
    Calculate LTV for subscribers vs non-subscribers.
    
    Hypothesis: Subscribers have higher LTV than non-subscribers.
    This helps justify subscription discount investments.
    """
    
    # Get all subscriber customer IDs
    subscriber_ids = subscriptions_df.select(
        "merchant_id",
        "customer_id"
    ).distinct().withColumn("is_subscriber", F.lit(True))
    
    # Calculate LTV from orders
    customer_ltv = orders_df.filter(
        F.col("status").isin(["delivered", "shipped", "confirmed"])
    ).groupBy(
        "merchant_id",
        "customer_id"
    ).agg(
        F.sum("total_amount").alias("ltv"),
        F.count("*").alias("order_count")
    )
    
    # Join to identify subscribers
    customer_ltv = customer_ltv.join(
        subscriber_ids,
        on=["merchant_id", "customer_id"],
        how="left"
    ).fillna({"is_subscriber": False})
    
    # Aggregate by subscriber status
    ltv_comparison = customer_ltv.groupBy(
        "merchant_id",
        "is_subscriber"
    ).agg(
        F.avg("ltv").alias("avg_ltv"),
        F.avg("order_count").alias("avg_orders"),
        F.count("*").alias("customer_count")
    )
    
    return ltv_comparison


def calculate_subscription_cohorts(subscriptions_df: DataFrame) -> DataFrame:
    """
    Calculate cohort-based retention metrics.
    
    Cohorts defined by subscription start month.
    Track retention at 1, 3, 6, 12 month intervals.
    """
    
    # Add cohort month
    subs_with_cohort = subscriptions_df.withColumn(
        "cohort_month",
        F.date_trunc("month", F.col("started_at"))
    )
    
    # Calculate tenure in months
    subs_with_cohort = subs_with_cohort.withColumn(
        "tenure_months",
        F.months_between(F.current_date(), F.col("started_at"))
    )
    
    # Aggregate by cohort
    cohort_metrics = subs_with_cohort.groupBy(
        "merchant_id",
        "cohort_month"
    ).agg(
        F.count("*").alias("cohort_size"),
        F.sum(F.when(F.col("status") == "active", 1).otherwise(0)).alias("still_active"),
        F.avg("total_orders_generated").alias("avg_orders_per_sub"),
        F.sum("total_revenue").alias("cohort_revenue"),
    )
    
    # Calculate retention rate
    cohort_metrics = cohort_metrics.withColumn(
        "retention_rate",
        F.col("still_active") / F.col("cohort_size")
    )
    
    return cohort_metrics


def build_subscription_metrics(spark: SparkSession) -> DataFrame:
    """
    Main transformation function to build agg_subscription_metrics table.
    """
    
    print("Building agg_subscription_metrics")
    
    # Extract data
    subscriptions_df = extract_subscriptions(spark)
    orders_df = read_from_warehouse(spark, table="raw.orders")
    
    # Calculate MRR
    subs_with_mrr = calculate_mrr(subscriptions_df)
    merchant_mrr = aggregate_merchant_mrr(subs_with_mrr)
    
    # Calculate churn
    churn_metrics = calculate_churn_metrics(subs_with_mrr)
    
    # Calculate subscriber LTV
    ltv_comparison = calculate_subscriber_ltv(subscriptions_df, orders_df)
    
    # Pivot LTV comparison for easier analysis
    subscriber_ltv = ltv_comparison.filter(F.col("is_subscriber") == True).select(
        "merchant_id",
        F.col("avg_ltv").alias("subscriber_avg_ltv"),
        F.col("avg_orders").alias("subscriber_avg_orders"),
        F.col("customer_count").alias("subscriber_count")
    )
    
    non_subscriber_ltv = ltv_comparison.filter(F.col("is_subscriber") == False).select(
        "merchant_id",
        F.col("avg_ltv").alias("non_subscriber_avg_ltv"),
        F.col("avg_orders").alias("non_subscriber_avg_orders")
    )
    
    # Join all metrics
    result = merchant_mrr \
        .join(churn_metrics, on="merchant_id", how="left") \
        .join(subscriber_ltv, on="merchant_id", how="left") \
        .join(non_subscriber_ltv, on="merchant_id", how="left")
    
    # Calculate LTV lift from subscriptions
    result = result.withColumn(
        "subscriber_ltv_lift",
        F.when(
            F.col("non_subscriber_avg_ltv") > 0,
            (F.col("subscriber_avg_ltv") - F.col("non_subscriber_avg_ltv")) / 
            F.col("non_subscriber_avg_ltv") * 100
        ).otherwise(0.0)
    )
    
    # Calculate churn rate
    result = result.withColumn(
        "churn_rate",
        F.when(
            (F.col("active_subscriptions") + F.coalesce(F.col("churned_subscriptions"), F.lit(0))) > 0,
            F.coalesce(F.col("churned_subscriptions"), F.lit(0)) /
            (F.col("active_subscriptions") + F.coalesce(F.col("churned_subscriptions"), F.lit(0)))
        ).otherwise(0.0)
    )
    
    # Add metadata
    result = result.withColumn("_loaded_at", F.current_timestamp())
    
    return result


def run_job():
    """Entry point for the ETL job."""
    
    spark = get_spark_session("etl_subscription_metrics")
    
    try:
        agg_subscription_metrics = build_subscription_metrics(spark)
        row_count = agg_subscription_metrics.count()
        
        write_to_warehouse(
            df=agg_subscription_metrics,
            table="marts.agg_subscription_metrics",
            mode="overwrite"
        )
        
        log_job_metrics(
            job_name="etl_subscription_metrics",
            run_date=datetime.now().strftime("%Y-%m-%d"),
            rows_processed=row_count,
            status="success"
        )
        
        print(f"Successfully wrote {row_count} rows to marts.agg_subscription_metrics")
        
    except Exception as e:
        log_job_metrics(
            job_name="etl_subscription_metrics",
            run_date=datetime.now().strftime("%Y-%m-%d"),
            rows_processed=0,
            status="failed",
            error=str(e)
        )
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    run_job()
