"""
Schema Definitions for Order-related Tables

Defines PySpark schemas for order data used in ETL pipelines.
Schemas ensure data consistency and enable schema evolution tracking.
"""

from pyspark.sql.types import (
    StructType, StructField, StringType, DecimalType, 
    IntegerType, TimestampType, BooleanType, ArrayType,
    MapType
)


# =============================================================================
# Raw Layer Schemas
# =============================================================================

RAW_ORDERS_SCHEMA = StructType([
    StructField("order_id", StringType(), False),
    StructField("merchant_id", StringType(), False),
    StructField("customer_id", StringType(), False),
    StructField("status", StringType(), False),
    
    # Channel and attribution
    StructField("channel", StringType(), True),
    StructField("utm_source", StringType(), True),
    StructField("utm_medium", StringType(), True),
    StructField("utm_campaign", StringType(), True),
    
    # Financials
    StructField("subtotal", DecimalType(12, 2), False),
    StructField("discount_amount", DecimalType(10, 2), True),
    StructField("tax_amount", DecimalType(10, 2), True),
    StructField("shipping_amount", DecimalType(10, 2), True),
    StructField("total_amount", DecimalType(12, 2), False),
    StructField("currency", StringType(), True),
    
    # Items
    StructField("item_count", IntegerType(), True),
    
    # Coupon/promo
    StructField("coupon_code", StringType(), True),
    StructField("promotion_id", StringType(), True),
    
    # Flags
    StructField("is_first_order", BooleanType(), True),
    StructField("is_gift", BooleanType(), True),
    
    # Risk
    StructField("risk_score", IntegerType(), True),
    
    # Timestamps
    StructField("created_at", TimestampType(), False),
    StructField("updated_at", TimestampType(), True),
    StructField("confirmed_at", TimestampType(), True),
    StructField("shipped_at", TimestampType(), True),
    StructField("delivered_at", TimestampType(), True),
])


RAW_ORDER_ITEMS_SCHEMA = StructType([
    StructField("order_item_id", StringType(), False),
    StructField("order_id", StringType(), False),
    StructField("product_id", StringType(), False),
    StructField("merchant_id", StringType(), False),
    
    # Product info at order time
    StructField("product_name", StringType(), True),
    StructField("product_sku", StringType(), True),
    StructField("variant_id", StringType(), True),
    
    # Quantity and pricing
    StructField("quantity", IntegerType(), False),
    StructField("unit_price", DecimalType(10, 2), False),
    StructField("discount_amount", DecimalType(10, 2), True),
    StructField("tax_amount", DecimalType(10, 2), True),
    StructField("line_subtotal", DecimalType(12, 2), True),
    StructField("total_amount", DecimalType(12, 2), False),
    
    # Fulfillment
    StructField("fulfillment_status", StringType(), True),
    
    # Cost (for margin calculation)
    StructField("unit_cost", DecimalType(10, 2), True),
    
    # Timestamps
    StructField("created_at", TimestampType(), False),
])


# =============================================================================
# Mart Layer Schemas
# =============================================================================

FACT_ORDERS_SCHEMA = StructType([
    # Keys
    StructField("order_id", StringType(), False),
    StructField("merchant_id", StringType(), False),
    StructField("customer_id", StringType(), False),
    
    # Order details
    StructField("status", StringType(), False),
    StructField("channel", StringType(), True),
    StructField("order_date", StringType(), False),  # Date string YYYY-MM-DD
    StructField("created_at", TimestampType(), False),
    
    # Financials
    StructField("subtotal", DecimalType(12, 2), False),
    StructField("discount_amount", DecimalType(10, 2), True),
    StructField("tax_amount", DecimalType(10, 2), True),
    StructField("shipping_amount", DecimalType(10, 2), True),
    StructField("total_amount", DecimalType(12, 2), False),
    StructField("gmv", DecimalType(12, 2), False),
    StructField("nmv", DecimalType(12, 2), True),
    
    # Item metrics
    StructField("item_count", IntegerType(), True),
    StructField("unique_products", IntegerType(), True),
    StructField("avg_item_price", DecimalType(10, 2), True),
    
    # Customer context
    StructField("customer_tier", StringType(), True),
    StructField("customer_ltv_at_order", DecimalType(12, 2), True),
    StructField("is_first_order", BooleanType(), True),
    StructField("days_since_prev_order", IntegerType(), True),
    
    # Time dimensions
    StructField("order_hour", IntegerType(), True),
    StructField("order_day_of_week", IntegerType(), True),
    StructField("order_week", IntegerType(), True),
    StructField("order_month", IntegerType(), True),
    StructField("order_quarter", IntegerType(), True),
    StructField("order_year", IntegerType(), True),
    StructField("is_weekend", BooleanType(), True),
    
    # Attribution
    StructField("utm_source", StringType(), True),
    StructField("utm_medium", StringType(), True),
    StructField("utm_campaign", StringType(), True),
    
    # Metadata
    StructField("_loaded_at", TimestampType(), False),
])


# =============================================================================
# Aggregation Schemas
# =============================================================================

AGG_DAILY_GMV_SCHEMA = StructType([
    StructField("merchant_id", StringType(), False),
    StructField("order_date", StringType(), False),
    
    # Core GMV metrics
    StructField("total_gmv", DecimalType(14, 2), True),
    StructField("total_nmv", DecimalType(14, 2), True),
    StructField("total_revenue", DecimalType(14, 2), True),
    
    # Order metrics
    StructField("order_count", IntegerType(), True),
    StructField("total_items_sold", IntegerType(), True),
    StructField("avg_order_value", DecimalType(10, 2), True),
    
    # Customer metrics
    StructField("unique_customers", IntegerType(), True),
    StructField("new_customers", IntegerType(), True),
    StructField("returning_customers", IntegerType(), True),
    StructField("new_customer_rate", DecimalType(5, 4), True),
    
    # Period comparisons
    StructField("gmv_dod_change", DecimalType(8, 2), True),
    StructField("gmv_wow_change", DecimalType(8, 2), True),
    
    # Rolling metrics
    StructField("gmv_7d_rolling", DecimalType(14, 2), True),
    StructField("gmv_30d_rolling", DecimalType(14, 2), True),
    
    # Metadata
    StructField("_loaded_at", TimestampType(), False),
])
