-- agg_daily_gmv.sql
-- Daily GMV aggregates by merchant
--
-- Owner: Data Engineering (@data-forge)
-- Schedule: Daily at 03:00 UTC (after fact_orders)
-- Dependencies: fact_orders
--
-- This table powers the Pulse dashboard GMV widgets
-- and is used for merchant tier calculations.
--
-- GMV = Gross Merchandise Value = sum of order subtotals
-- Excludes cancelled and refunded orders.

{{
    config(
        materialized='incremental',
        unique_key='merchant_date_key',
        incremental_strategy='merge'
    )
}}

with orders as (
    select * from {{ ref('fact_orders') }}
    where order_status_category != 'cancelled'
    
    {% if is_incremental() %}
    and order_date >= dateadd('day', -3, current_date)
    {% endif %}
),

daily_aggregates as (
    select
        -- Composite key
        concat(merchant_id, '_', order_date) as merchant_date_key,
        
        -- Dimensions
        merchant_id,
        merchant_name,
        merchant_tier,
        order_date,
        
        -- GMV metrics
        sum(gmv) as gmv,
        sum(net_revenue) as net_revenue,
        sum(total_amount) as gross_revenue,
        sum(refund_amount) as refund_amount,
        sum(discount_amount) as discount_amount,
        sum(shipping_amount) as shipping_revenue,
        
        -- Order counts
        count(distinct order_id) as order_count,
        count(distinct customer_id) as unique_customers,
        count(distinct case when is_first_order then customer_id end) as new_customers,
        
        -- Item metrics
        sum(item_count) as total_items,
        avg(item_count) as avg_items_per_order,
        
        -- Average order value
        avg(total_amount) as average_order_value,
        
        -- Recommendation attribution
        sum(case when has_recommended_items then 1 else 0 end) as orders_with_recommendations,
        sum(recommended_items_value) as recommendation_attributed_revenue,
        sum(recommended_items_value) / nullif(sum(gmv), 0) as recommendation_revenue_share,
        
        -- Channel breakdown
        sum(case when channel_grouping = 'Direct' then gmv else 0 end) as gmv_direct,
        sum(case when channel_grouping = 'Paid Search' then gmv else 0 end) as gmv_paid_search,
        sum(case when channel_grouping = 'Organic Search' then gmv else 0 end) as gmv_organic_search,
        sum(case when channel_grouping = 'Paid Social' then gmv else 0 end) as gmv_paid_social,
        sum(case when channel_grouping = 'Email' then gmv else 0 end) as gmv_email,
        sum(case when channel_grouping = 'Referral' then gmv else 0 end) as gmv_referral,
        
        -- Customer tier breakdown
        sum(case when customer_tier = 'platinum' then gmv else 0 end) as gmv_platinum_customers,
        sum(case when customer_tier = 'gold' then gmv else 0 end) as gmv_gold_customers,
        sum(case when customer_tier = 'silver' then gmv else 0 end) as gmv_silver_customers,
        sum(case when customer_tier = 'bronze' then gmv else 0 end) as gmv_bronze_customers,
        
        -- Coupon usage
        sum(case when has_coupon then 1 else 0 end) as orders_with_coupon,
        sum(case when has_coupon then discount_amount else 0 end) as coupon_discount_total,
        
        -- Fulfillment metrics
        avg(hours_to_ship) as avg_hours_to_ship,
        
        -- Timestamps
        current_timestamp as dbt_updated_at
        
    from orders
    group by 1, 2, 3, 4, 5
),

-- Add period-over-period comparisons
with_comparisons as (
    select
        d.*,
        
        -- Previous day
        lag(gmv, 1) over (partition by merchant_id order by order_date) as gmv_prev_day,
        
        -- Same day last week
        lag(gmv, 7) over (partition by merchant_id order by order_date) as gmv_same_day_last_week,
        
        -- Same day last month (approximation)
        lag(gmv, 30) over (partition by merchant_id order by order_date) as gmv_same_day_last_month,
        
        -- Rolling 7-day GMV
        sum(gmv) over (
            partition by merchant_id 
            order by order_date 
            rows between 6 preceding and current row
        ) as gmv_rolling_7d,
        
        -- Rolling 30-day GMV
        sum(gmv) over (
            partition by merchant_id 
            order by order_date 
            rows between 29 preceding and current row
        ) as gmv_rolling_30d,
        
        -- Month-to-date GMV
        sum(gmv) over (
            partition by merchant_id, date_trunc('month', order_date) 
            order by order_date
        ) as gmv_mtd
        
    from daily_aggregates d
)

select
    *,
    
    -- Calculate change percentages
    case 
        when gmv_prev_day > 0 
        then (gmv - gmv_prev_day) / gmv_prev_day * 100 
        else null 
    end as gmv_change_vs_prev_day_pct,
    
    case 
        when gmv_same_day_last_week > 0 
        then (gmv - gmv_same_day_last_week) / gmv_same_day_last_week * 100 
        else null 
    end as gmv_change_vs_last_week_pct

from with_comparisons
