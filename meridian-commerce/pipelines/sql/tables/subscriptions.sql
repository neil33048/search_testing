-- Subscriptions table definition
--
-- Recurring order subscriptions (subscribe & save, replenishment).
-- Generates orders automatically on schedule.
--
-- Subscription Status:
--   - active: Currently running, will generate next order
--   - paused: Temporarily stopped, can resume
--   - cancelled: Permanently stopped
--   - expired: Reached end date
--   - payment_failed: On hold due to payment issues
--
-- Billing Frequencies:
--   - weekly, biweekly, monthly, bimonthly, quarterly, annually
--
-- Discount Logic:
--   - Subscribers typically get 5-20% off vs one-time purchase
--   - Discount may increase with tenure (loyalty)
--
-- Owner: Subscriptions Team
-- Related: orders, customers, products

CREATE TABLE IF NOT EXISTS subscriptions (
    -- Primary key with 'sub_' prefix
    id VARCHAR(18) PRIMARY KEY,
    
    -- Foreign keys
    merchant_id VARCHAR(18) NOT NULL REFERENCES merchants(id),
    customer_id VARCHAR(18) NOT NULL REFERENCES customers(id),
    
    -- Subscription name (for display)
    name VARCHAR(255),
    
    -- Status
    status VARCHAR(20) DEFAULT 'active' 
        CHECK (status IN ('active', 'paused', 'cancelled', 'expired', 'payment_failed')),
    
    -- Pause info
    paused_at TIMESTAMP,
    pause_reason VARCHAR(255),
    resume_at TIMESTAMP,  -- Scheduled resume date (for vacation pause)
    
    -- Cancellation info
    cancelled_at TIMESTAMP,
    cancellation_reason VARCHAR(255),
    -- cancellation_type: 'customer' or 'merchant' or 'system'
    cancellation_type VARCHAR(20),
    
    -- Billing schedule
    -- frequency: How often to bill
    -- interval_count: Number of intervals (e.g., 2 with 'weekly' = every 2 weeks)
    frequency VARCHAR(20) NOT NULL 
        CHECK (frequency IN ('weekly', 'biweekly', 'monthly', 'bimonthly', 'quarterly', 'annually')),
    interval_count INTEGER DEFAULT 1,
    
    -- Billing day
    -- billing_day_of_week: 1=Monday, 7=Sunday (for weekly)
    -- billing_day_of_month: 1-28 (for monthly)
    billing_day_of_week INTEGER CHECK (billing_day_of_week BETWEEN 1 AND 7),
    billing_day_of_month INTEGER CHECK (billing_day_of_month BETWEEN 1 AND 28),
    
    -- Next order date
    next_order_at TIMESTAMP,
    
    -- Subscription items (JSONB array)
    -- Example: [{"product_id": "prod_xxx", "quantity": 2, "unit_price": 19.99}]
    items JSONB NOT NULL,
    
    -- Pricing
    subtotal DECIMAL(10, 2) NOT NULL,  -- Before discounts
    discount_amount DECIMAL(10, 2) DEFAULT 0,
    discount_percent DECIMAL(5, 2) DEFAULT 0,  -- e.g., 15 = 15% off
    
    -- Shipping
    shipping_amount DECIMAL(10, 2) DEFAULT 0,
    shipping_address JSONB,  -- Full address object
    
    -- Total per cycle = subtotal - discount + shipping + tax
    estimated_tax DECIMAL(10, 2) DEFAULT 0,
    estimated_total DECIMAL(10, 2) NOT NULL,
    
    -- Payment method (saved for recurring billing)
    payment_method_id VARCHAR(50),  -- Reference to saved payment method
    
    -- Retry logic for failed payments
    payment_retry_count INTEGER DEFAULT 0,
    max_payment_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP,
    last_payment_error VARCHAR(255),
    
    -- History
    total_orders_generated INTEGER DEFAULT 0,
    total_revenue DECIMAL(14, 2) DEFAULT 0,
    last_order_id VARCHAR(20),
    last_order_at TIMESTAMP,
    
    -- Tenure/loyalty
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- tenure_months: Calculated for loyalty discounts
    
    -- Optional end date
    ends_at TIMESTAMP,  -- NULL = ongoing
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_subscriptions_merchant_id ON subscriptions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer_id ON subscriptions(customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_next_order ON subscriptions(next_order_at) 
    WHERE status = 'active';

-- Comments
COMMENT ON TABLE subscriptions IS 'Recurring order subscriptions (subscribe & save)';
COMMENT ON COLUMN subscriptions.frequency IS 'Billing frequency: weekly, biweekly, monthly, bimonthly, quarterly, annually';
COMMENT ON COLUMN subscriptions.items IS 'JSONB array of subscription items with product_id, quantity, unit_price';
COMMENT ON COLUMN subscriptions.discount_percent IS 'Subscriber discount percentage (e.g., 15 = 15% off)';
