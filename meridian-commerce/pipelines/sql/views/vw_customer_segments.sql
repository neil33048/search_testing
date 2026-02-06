-- Customer Segments View
--
-- Provides customer segmentation for analytics and marketing.
-- Uses RFM (Recency, Frequency, Monetary) analysis.
--
-- Owner: Analytics Team
-- Refreshed: Daily via Pulse

CREATE OR REPLACE VIEW vw_customer_segments AS
WITH customer_metrics AS (
    SELECT
        c.id AS customer_id,
        c.merchant_id,
        c.email,
        c.first_name,
        c.last_name,
        c.tier,
        c.ltv,
        c.total_orders,
        c.last_order_at,
        c.created_at,
        
        -- Recency: Days since last order
        DATEDIFF(day, c.last_order_at, CURRENT_DATE) AS days_since_last_order,
        
        -- Frequency: Orders per month (normalized)
        CASE 
            WHEN DATEDIFF(month, c.created_at, CURRENT_DATE) > 0
            THEN c.total_orders / DATEDIFF(month, c.created_at, CURRENT_DATE)
            ELSE c.total_orders
        END AS orders_per_month,
        
        -- Monetary: Average order value
        CASE 
            WHEN c.total_orders > 0 
            THEN c.ltv / c.total_orders 
            ELSE 0 
        END AS avg_order_value
        
    FROM customers c
    WHERE c.status = 'active'
),

rfm_scores AS (
    SELECT
        *,
        
        -- Recency score (1-5, higher is better/more recent)
        CASE
            WHEN days_since_last_order <= 7 THEN 5
            WHEN days_since_last_order <= 30 THEN 4
            WHEN days_since_last_order <= 90 THEN 3
            WHEN days_since_last_order <= 180 THEN 2
            ELSE 1
        END AS recency_score,
        
        -- Frequency score (1-5, higher is more frequent)
        CASE
            WHEN orders_per_month >= 2 THEN 5
            WHEN orders_per_month >= 1 THEN 4
            WHEN orders_per_month >= 0.5 THEN 3
            WHEN orders_per_month >= 0.25 THEN 2
            ELSE 1
        END AS frequency_score,
        
        -- Monetary score (1-5, higher is higher value)
        CASE
            WHEN avg_order_value >= 200 THEN 5
            WHEN avg_order_value >= 100 THEN 4
            WHEN avg_order_value >= 50 THEN 3
            WHEN avg_order_value >= 25 THEN 2
            ELSE 1
        END AS monetary_score
        
    FROM customer_metrics
)

SELECT
    customer_id,
    merchant_id,
    email,
    first_name,
    last_name,
    tier,
    ltv,
    total_orders,
    last_order_at,
    days_since_last_order,
    orders_per_month,
    avg_order_value,
    recency_score,
    frequency_score,
    monetary_score,
    
    -- Combined RFM score
    recency_score + frequency_score + monetary_score AS rfm_score,
    
    -- Customer segment based on RFM
    CASE
        -- Champions: High recency, frequency, and monetary
        WHEN recency_score >= 4 AND frequency_score >= 4 AND monetary_score >= 4 
            THEN 'champion'
        
        -- Loyal: High frequency, moderate recency
        WHEN frequency_score >= 4 AND recency_score >= 3 
            THEN 'loyal'
        
        -- Promising: High recency, low frequency (new but engaged)
        WHEN recency_score >= 4 AND frequency_score <= 2 
            THEN 'promising'
        
        -- At Risk: Were loyal but haven't purchased recently
        WHEN recency_score <= 2 AND frequency_score >= 3 
            THEN 'at_risk'
        
        -- Needs Attention: Moderate across all
        WHEN recency_score = 3 AND frequency_score = 3 
            THEN 'needs_attention'
        
        -- Hibernating: Low recency and frequency
        WHEN recency_score <= 2 AND frequency_score <= 2 
            THEN 'hibernating'
        
        -- Default segment
        ELSE 'regular'
    END AS segment,
    
    -- Churn risk score (0-1)
    CASE
        WHEN days_since_last_order > 365 THEN 0.95
        WHEN days_since_last_order > 180 THEN 0.75
        WHEN days_since_last_order > 90 THEN 0.50
        WHEN days_since_last_order > 30 THEN 0.25
        ELSE 0.10
    END AS churn_risk

FROM rfm_scores;

COMMENT ON VIEW vw_customer_segments IS 'Customer segments using RFM analysis for marketing targeting';
