-- stg_orders.sql
-- Staging model for orders data
-- 
-- Owner: Data Engineering (@data-forge)
-- Source: PostgreSQL transactional database
-- Schedule: Incremental, hourly
--
-- This model cleans and types raw order data from the
-- transactional database for downstream transformations.

{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='merge'
    )
}}

with source as (
    select * from {{ source('transactional', 'orders') }}
    
    {% if is_incremental() %}
    where updated_at > (select max(updated_at) from {{ this }})
    {% endif %}
),

renamed as (
    select
        -- Primary key
        id as order_id,
        
        -- Foreign keys
        merchant_id,
        customer_id,
        
        -- External reference
        external_id as external_order_id,
        
        -- Status
        status as order_status,
        
        -- Amounts (cast to numeric for precision)
        cast(subtotal as numeric(12, 2)) as subtotal,
        cast(tax_amount as numeric(12, 2)) as tax_amount,
        cast(shipping_amount as numeric(12, 2)) as shipping_amount,
        cast(discount_amount as numeric(12, 2)) as discount_amount,
        cast(total_amount as numeric(12, 2)) as total_amount,
        
        -- Currency
        coalesce(currency, 'USD') as currency,
        
        -- Item counts
        item_count,
        unique_item_count,
        
        -- Payment
        payment_method,
        payment_id,
        paid_at,
        
        -- Fulfillment
        fulfillment_method,
        shipped_at,
        delivered_at,
        tracking_number,
        carrier,
        
        -- Shipping address
        shipping_city,
        shipping_state,
        shipping_postal_code,
        shipping_country_code,
        
        -- Attribution
        source as traffic_source,
        medium as traffic_medium,
        campaign as campaign_name,
        
        -- Recommendations
        has_recommended_items,
        cast(recommended_items_value as numeric(12, 2)) as recommended_items_value,
        
        -- Refund
        refunded_at,
        cast(refund_amount as numeric(12, 2)) as refund_amount,
        refund_reason,
        
        -- Coupon
        coupon_code,
        
        -- Timestamps
        created_at,
        updated_at,
        cancelled_at,
        
        -- Metadata
        metadata
        
    from source
    
    -- Exclude test/internal orders
    where merchant_id not in ('merch_test', 'merch_internal')
      and status != 'test'
)

select * from renamed
