{{
    config(
        materialized='incremental',
        unique_key='order_item_id',
        cluster_by=['merchant_id', 'order_date']
    )
}}

/*
    Intermediate Order Items Model
    
    Joins order items with product and order data for downstream aggregations.
    Used by fact_orders and various aggregation models.
    
    Grain: One row per order item
    Owner: Data Engineering
*/

WITH order_items AS (
    SELECT
        oi.id AS order_item_id,
        oi.order_id,
        oi.product_id,
        oi.quantity,
        oi.unit_price,
        oi.discount_amount,
        oi.tax_amount,
        oi.total_amount
    FROM {{ ref('stg_order_items') }} oi
    {% if is_incremental() %}
    WHERE oi._loaded_at > (SELECT MAX(_loaded_at) FROM {{ this }})
    {% endif %}
),

orders AS (
    SELECT
        o.order_id,
        o.merchant_id,
        o.customer_id,
        o.order_status,
        o.order_date,
        o.created_at AS order_created_at
    FROM {{ ref('stg_orders') }} o
),

products AS (
    SELECT
        p.product_id,
        p.product_name,
        p.sku,
        p.category_path,
        p.category_l1,
        p.category_l2
    FROM {{ ref('stg_products') }} p
)

SELECT
    -- Keys
    oi.order_item_id,
    oi.order_id,
    o.merchant_id,
    o.customer_id,
    oi.product_id,
    
    -- Order attributes
    o.order_status,
    o.order_date,
    o.order_created_at,
    
    -- Product attributes
    p.product_name,
    p.sku,
    p.category_path,
    p.category_l1,
    p.category_l2,
    
    -- Item metrics
    oi.quantity,
    oi.unit_price,
    oi.discount_amount,
    oi.tax_amount,
    oi.total_amount,
    
    -- Calculated fields
    -- Gross merchandise value (before discounts)
    oi.quantity * oi.unit_price AS gmv,
    
    -- Net merchandise value (after discounts, before tax)
    (oi.quantity * oi.unit_price) - oi.discount_amount AS nmv,
    
    -- Average unit price after discount
    CASE 
        WHEN oi.quantity > 0 
        THEN (oi.total_amount - oi.tax_amount) / oi.quantity
        ELSE 0 
    END AS effective_unit_price,
    
    -- Discount rate
    CASE 
        WHEN oi.quantity * oi.unit_price > 0 
        THEN oi.discount_amount / (oi.quantity * oi.unit_price)
        ELSE 0 
    END AS discount_rate,
    
    -- Audit columns
    CURRENT_TIMESTAMP AS _loaded_at

FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN products p ON oi.product_id = p.product_id
