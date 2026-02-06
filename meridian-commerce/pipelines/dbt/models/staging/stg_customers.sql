-- stg_customers.sql
-- Staging model for customer data
--
-- Owner: Data Engineering (@data-forge)
-- Source: PostgreSQL transactional database
-- Schedule: Incremental, hourly

{{
    config(
        materialized='incremental',
        unique_key='customer_id',
        incremental_strategy='merge'
    )
}}

with source as (
    select * from {{ source('transactional', 'customers') }}
    
    {% if is_incremental() %}
    where updated_at > (select max(updated_at) from {{ this }})
    {% endif %}
),

renamed as (
    select
        -- Primary key
        id as customer_id,
        
        -- Foreign keys
        merchant_id,
        
        -- Contact info
        email,
        email_verified,
        phone,
        phone_verified,
        
        -- Profile
        first_name,
        last_name,
        concat(
            coalesce(first_name, ''),
            ' ',
            coalesce(last_name, '')
        ) as full_name,
        
        -- Segmentation
        tier as customer_tier,
        segment as customer_segment,
        
        -- Metrics (from source, may need recalculation)
        cast(ltv as numeric(12, 2)) as ltv,
        total_orders,
        cast(total_spent as numeric(12, 2)) as total_spent,
        cast(average_order_value as numeric(12, 2)) as average_order_value,
        
        -- Activity timestamps
        first_order_at,
        last_order_at,
        
        -- Marketing
        accepts_marketing,
        marketing_opt_in_at,
        
        -- Status
        is_active,
        
        -- Timestamps
        created_at,
        updated_at,
        deleted_at,
        
        -- Metadata
        metadata
        
    from source
    
    -- Exclude deleted customers
    where deleted_at is null
)

select * from renamed
