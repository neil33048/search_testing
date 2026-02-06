-- dim_customers.sql
-- Customer dimension table with calculated metrics and tier assignment
--
-- Owner: Data Engineering (@data-forge)
-- Schedule: Daily at 02:00 UTC
-- Dependencies: stg_customers, stg_orders
--
-- This is the primary customer dimension used by Pulse dashboards
-- and Catalyst recommendation models.
--
-- IMPORTANT: Customer tier thresholds are defined in dbt_project.yml
-- Changes to tier logic must be approved by Growth team.

{{
    config(
        materialized='table',
        unique_key='customer_id'
    )
}}

with customers as (
    select * from {{ ref('stg_customers') }}
),

-- Calculate order-based metrics from orders
order_metrics as (
    select
        customer_id,
        count(*) as calculated_order_count,
        sum(total_amount) as calculated_total_spent,
        avg(total_amount) as calculated_aov,
        min(created_at) as calculated_first_order_at,
        max(created_at) as calculated_last_order_at,
        sum(subtotal) as gmv,  -- GMV = subtotals only
        sum(case when has_recommended_items then recommended_items_value else 0 end) as rec_attributed_revenue
    from {{ ref('stg_orders') }}
    where order_status not in ('cancelled', 'refunded')
    group by 1
),

-- Calculate LTV with 12-month rolling window
-- LTV = total revenue minus refunds
ltv_calculation as (
    select
        customer_id,
        sum(total_amount - coalesce(refund_amount, 0)) as calculated_ltv
    from {{ ref('stg_orders') }}
    where order_status not in ('cancelled')
      and created_at >= dateadd('month', -12, current_date)
    group by 1
),

-- Determine customer tier based on LTV
-- Tiers: Platinum (>$5000), Gold (>$1000), Silver (>$250), Bronze (else)
-- 
-- Legacy note: Old system used tier1-tier4 numbering
-- tier1 = Platinum, tier2 = Gold, tier3 = Silver, tier4 = Bronze
tier_assignment as (
    select
        customer_id,
        calculated_ltv,
        case
            when calculated_ltv >= 5000 then 'platinum'
            when calculated_ltv >= 1000 then 'gold'
            when calculated_ltv >= 250 then 'silver'
            else 'bronze'
        end as calculated_tier
    from ltv_calculation
),

-- Determine customer segment based on activity
segment_assignment as (
    select
        customer_id,
        calculated_last_order_at,
        datediff('day', calculated_last_order_at, current_date) as days_since_last_order,
        case
            when datediff('day', calculated_first_order_at, current_date) <= 30 then 'new'
            when calculated_ltv >= 5000 and calculated_order_count >= 10 then 'vip'
            when datediff('day', calculated_last_order_at, current_date) <= 90 then 'active'
            when datediff('day', calculated_last_order_at, current_date) <= {{ var('at_risk_threshold_days') }} then 'at_risk'
            when datediff('day', calculated_last_order_at, current_date) > {{ var('churn_threshold_days') }} then 'churned'
            else 'active'
        end as calculated_segment
    from order_metrics
    left join ltv_calculation using (customer_id)
),

final as (
    select
        -- Customer identifiers
        c.customer_id,
        c.merchant_id,
        
        -- Contact info
        c.email,
        c.email_verified,
        c.phone,
        c.phone_verified,
        
        -- Profile
        c.first_name,
        c.last_name,
        c.full_name,
        
        -- Calculated tier (overrides source tier)
        coalesce(t.calculated_tier, c.customer_tier, 'bronze') as customer_tier,
        
        -- Calculated segment (overrides source segment)
        coalesce(s.calculated_segment, c.customer_segment) as customer_segment,
        
        -- LTV (12-month rolling)
        coalesce(t.calculated_ltv, c.ltv, 0) as ltv,
        
        -- Order metrics
        coalesce(o.calculated_order_count, c.total_orders, 0) as total_orders,
        coalesce(o.calculated_total_spent, c.total_spent, 0) as total_spent,
        coalesce(o.calculated_aov, c.average_order_value, 0) as average_order_value,
        coalesce(o.gmv, 0) as total_gmv,
        
        -- Catalyst attribution
        coalesce(o.rec_attributed_revenue, 0) as recommendation_attributed_revenue,
        
        -- Activity
        coalesce(o.calculated_first_order_at, c.first_order_at) as first_order_at,
        coalesce(o.calculated_last_order_at, c.last_order_at) as last_order_at,
        coalesce(s.days_since_last_order, 0) as days_since_last_order,
        
        -- Churn indicator
        case
            when s.days_since_last_order > {{ var('churn_threshold_days') }} then true
            else false
        end as is_churned,
        
        -- Marketing
        c.accepts_marketing,
        c.marketing_opt_in_at,
        
        -- Status
        c.is_active,
        
        -- Timestamps
        c.created_at,
        c.updated_at,
        current_timestamp as dbt_updated_at
        
    from customers c
    left join order_metrics o on c.customer_id = o.customer_id
    left join tier_assignment t on c.customer_id = t.customer_id
    left join segment_assignment s on c.customer_id = s.customer_id
)

select * from final
