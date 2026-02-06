{{
    config(
        materialized='table',
        cluster_by=['merchant_id']
    )
}}

/*
    Merchant Performance Aggregation
    
    Daily performance metrics for each merchant.
    Powers the Pulse merchant dashboard and tier calculations.
    
    Key Metrics:
    - GMV (Gross Merchandise Value)
    - Order counts and AOV
    - Conversion rates
    - Customer acquisition
    
    Grain: One row per merchant per day
    Owner: Analytics Team
*/

WITH daily_orders AS (
    SELECT
        merchant_id,
        DATE_TRUNC('day', order_date) AS report_date,
        
        -- Order metrics
        COUNT(DISTINCT order_id) AS order_count,
        SUM(subtotal) AS gmv,
        SUM(total_amount) AS revenue,
        SUM(item_count) AS units_sold,
        
        -- Customer metrics
        COUNT(DISTINCT customer_id) AS ordering_customers,
        COUNT(DISTINCT CASE 
            WHEN is_first_order THEN customer_id 
        END) AS new_customers,
        
        -- Average order value
        AVG(subtotal) AS avg_order_value,
        
        -- Order distribution
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY subtotal) AS median_order_value,
        MAX(subtotal) AS max_order_value
        
    FROM {{ ref('fact_orders') }}
    WHERE order_status NOT IN ('cancelled', 'refunded')
    GROUP BY 1, 2
),

daily_sessions AS (
    SELECT
        merchant_id,
        DATE_TRUNC('day', session_date) AS report_date,
        
        -- Session metrics
        COUNT(DISTINCT session_id) AS sessions,
        COUNT(DISTINCT anonymous_id) AS unique_visitors,
        
        -- Page views
        SUM(page_views) AS page_views,
        AVG(page_views) AS avg_pages_per_session,
        
        -- Bounce rate
        SUM(CASE WHEN page_views = 1 THEN 1 ELSE 0 END)::FLOAT / 
            NULLIF(COUNT(*), 0) AS bounce_rate,
            
        -- Product engagement
        COUNT(DISTINCT CASE 
            WHEN has_product_view THEN session_id 
        END) AS sessions_with_product_view,
        
        COUNT(DISTINCT CASE 
            WHEN has_add_to_cart THEN session_id 
        END) AS sessions_with_add_to_cart
        
    FROM {{ ref('fact_sessions') }}
    GROUP BY 1, 2
)

SELECT
    o.merchant_id,
    o.report_date,
    
    -- === Order Metrics ===
    o.order_count,
    o.gmv,
    o.revenue,
    o.units_sold,
    o.avg_order_value,
    o.median_order_value,
    o.max_order_value,
    
    -- === Customer Metrics ===
    o.ordering_customers,
    o.new_customers,
    o.ordering_customers - o.new_customers AS returning_customers,
    
    -- New customer rate
    CASE 
        WHEN o.ordering_customers > 0 
        THEN o.new_customers::FLOAT / o.ordering_customers
        ELSE 0 
    END AS new_customer_rate,
    
    -- === Session Metrics ===
    COALESCE(s.sessions, 0) AS sessions,
    COALESCE(s.unique_visitors, 0) AS unique_visitors,
    COALESCE(s.page_views, 0) AS page_views,
    COALESCE(s.avg_pages_per_session, 0) AS avg_pages_per_session,
    COALESCE(s.bounce_rate, 0) AS bounce_rate,
    
    -- === Conversion Metrics ===
    -- Overall conversion rate (orders / sessions)
    CASE 
        WHEN COALESCE(s.sessions, 0) > 0 
        THEN o.order_count::FLOAT / s.sessions
        ELSE 0 
    END AS conversion_rate,
    
    -- Product view rate
    CASE 
        WHEN COALESCE(s.sessions, 0) > 0 
        THEN COALESCE(s.sessions_with_product_view, 0)::FLOAT / s.sessions
        ELSE 0 
    END AS product_view_rate,
    
    -- Add to cart rate
    CASE 
        WHEN COALESCE(s.sessions, 0) > 0 
        THEN COALESCE(s.sessions_with_add_to_cart, 0)::FLOAT / s.sessions
        ELSE 0 
    END AS add_to_cart_rate,
    
    -- Cart to checkout rate
    CASE 
        WHEN COALESCE(s.sessions_with_add_to_cart, 0) > 0 
        THEN o.order_count::FLOAT / s.sessions_with_add_to_cart
        ELSE 0 
    END AS cart_to_checkout_rate,
    
    -- === Derived Metrics ===
    -- Revenue per session
    CASE 
        WHEN COALESCE(s.sessions, 0) > 0 
        THEN o.revenue / s.sessions
        ELSE 0 
    END AS revenue_per_session,
    
    -- Revenue per visitor
    CASE 
        WHEN COALESCE(s.unique_visitors, 0) > 0 
        THEN o.revenue / s.unique_visitors
        ELSE 0 
    END AS revenue_per_visitor,
    
    -- Units per order
    CASE 
        WHEN o.order_count > 0 
        THEN o.units_sold::FLOAT / o.order_count
        ELSE 0 
    END AS units_per_order,
    
    -- Audit
    CURRENT_TIMESTAMP AS _loaded_at

FROM daily_orders o
LEFT JOIN daily_sessions s 
    ON o.merchant_id = s.merchant_id 
    AND o.report_date = s.report_date
