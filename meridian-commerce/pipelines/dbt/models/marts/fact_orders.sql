-- fact_orders.sql
-- Order fact table with denormalized dimensions
--
-- Owner: Data Engineering (@data-forge)
-- Schedule: Incremental, hourly
-- Dependencies: stg_orders, dim_customers, dim_products
--
-- This is the primary order fact table used for:
-- - GMV calculations
-- - Revenue analytics
-- - Merchant tier assessment
-- - Catalyst attribution

{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='merge',
        partition_by={
            'field': 'order_date',
            'data_type': 'date',
            'granularity': 'day'
        }
    )
}}

with orders as (
    select * from {{ ref('stg_orders') }}
    
    {% if is_incremental() %}
    where updated_at > (select max(updated_at) from {{ this }})
    {% endif %}
),

customers as (
    select * from {{ ref('dim_customers') }}
),

-- Add merchant tier lookup
merchants as (
    select
        merchant_id,
        tier as merchant_tier,
        name as merchant_name,
        industry as merchant_industry
    from {{ source('transactional', 'merchants') }}
),

final as (
    select
        -- Order grain
        o.order_id,
        o.external_order_id,
        
        -- Date dimensions
        date(o.created_at) as order_date,
        date_trunc('week', o.created_at) as order_week,
        date_trunc('month', o.created_at) as order_month,
        extract(hour from o.created_at) as order_hour,
        extract(dow from o.created_at) as order_day_of_week,
        
        -- Merchant dimension
        o.merchant_id,
        m.merchant_name,
        m.merchant_tier,
        m.merchant_industry,
        
        -- Customer dimension
        o.customer_id,
        c.customer_tier,
        c.customer_segment,
        c.ltv as customer_ltv,
        c.total_orders as customer_total_orders,
        c.is_churned as customer_is_churned,
        
        -- Is this customer's first order?
        case
            when c.first_order_at = o.created_at then true
            else false
        end as is_first_order,
        
        -- Order status
        o.order_status,
        case
            when o.order_status in ('delivered', 'shipped') then 'fulfilled'
            when o.order_status in ('cancelled', 'refunded') then 'cancelled'
            when o.order_status in ('pending', 'confirmed', 'processing') then 'in_progress'
            else 'other'
        end as order_status_category,
        
        -- Amounts
        o.subtotal,
        o.tax_amount,
        o.shipping_amount,
        o.discount_amount,
        o.total_amount,
        o.refund_amount,
        
        -- Net revenue (total - refunds)
        o.total_amount - coalesce(o.refund_amount, 0) as net_revenue,
        
        -- GMV (Gross Merchandise Value = subtotal only)
        -- This is the key metric for merchant tier calculations
        o.subtotal as gmv,
        
        -- Currency
        o.currency,
        
        -- Item metrics
        o.item_count,
        o.unique_item_count,
        
        -- Payment
        o.payment_method,
        o.paid_at,
        case when o.paid_at is not null then true else false end as is_paid,
        
        -- Fulfillment
        o.fulfillment_method,
        o.shipped_at,
        o.delivered_at,
        o.carrier,
        
        -- Time to fulfill (hours)
        case
            when o.shipped_at is not null
            then datediff('hour', o.created_at, o.shipped_at)
            else null
        end as hours_to_ship,
        
        case
            when o.delivered_at is not null
            then datediff('hour', o.shipped_at, o.delivered_at)
            else null
        end as hours_in_transit,
        
        -- Geography
        o.shipping_city,
        o.shipping_state,
        o.shipping_postal_code,
        o.shipping_country_code,
        
        -- Attribution
        o.traffic_source,
        o.traffic_medium,
        o.campaign_name,
        
        -- Channel grouping
        case
            when o.traffic_source = 'direct' or o.traffic_source is null then 'Direct'
            when o.traffic_medium = 'cpc' then 'Paid Search'
            when o.traffic_medium = 'organic' then 'Organic Search'
            when o.traffic_source like '%facebook%' or o.traffic_source like '%instagram%' then 'Paid Social'
            when o.traffic_medium = 'email' then 'Email'
            when o.traffic_medium = 'referral' then 'Referral'
            else 'Other'
        end as channel_grouping,
        
        -- Catalyst (recommendation) attribution
        o.has_recommended_items,
        o.recommended_items_value,
        case
            when o.has_recommended_items then o.recommended_items_value / nullif(o.subtotal, 0)
            else 0
        end as recommendation_revenue_share,
        
        -- Coupon
        o.coupon_code,
        case when o.coupon_code is not null then true else false end as has_coupon,
        
        -- Refund
        o.refunded_at,
        o.refund_reason,
        case when o.refunded_at is not null then true else false end as is_refunded,
        
        -- Timestamps
        o.created_at,
        o.updated_at,
        o.cancelled_at,
        current_timestamp as dbt_updated_at
        
    from orders o
    left join customers c on o.customer_id = c.customer_id
    left join merchants m on o.merchant_id = m.merchant_id
)

select * from final
