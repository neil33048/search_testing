"""
PySpark ETL Jobs

This package contains the ETL jobs that power Meridian Commerce analytics.

Jobs:
    - etl_orders_fact: Builds fact_orders table from raw orders
    - etl_customer_dim: Builds dim_customers with LTV and segmentation
    - etl_daily_gmv_agg: Aggregates daily GMV metrics
    - etl_product_analytics: Product performance analytics
    - etl_subscription_metrics: Subscription/MRR analytics

Tables Created:
    - marts.fact_orders
    - marts.dim_customers
    - marts.agg_daily_gmv
    - marts.agg_product_performance
    - marts.agg_subscription_metrics
"""
