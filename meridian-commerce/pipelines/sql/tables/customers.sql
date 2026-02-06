-- Customers table definition
--
-- Stores customer data for each merchant.
-- Customers are unique per merchant (same email can exist across merchants).
--
-- Owner: Data Engineering
-- Related: orders, events

CREATE TABLE IF NOT EXISTS customers (
    -- Primary key
    id VARCHAR(18) PRIMARY KEY,
    
    -- Foreign key to merchant
    merchant_id VARCHAR(18) NOT NULL REFERENCES merchants(id),
    
    -- Customer identification
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    
    -- Profile info
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    
    -- Customer tier based on LTV
    -- Values: bronze, silver, gold, platinum
    -- Note: Legacy systems used tier1-tier4 (tier1=platinum)
    tier VARCHAR(20) DEFAULT 'bronze',
    
    -- Lifetime value (sum of all orders)
    ltv DECIMAL(12, 2) DEFAULT 0,
    
    -- Order statistics
    total_orders INTEGER DEFAULT 0,
    total_spent DECIMAL(12, 2) DEFAULT 0,
    average_order_value DECIMAL(10, 2) DEFAULT 0,
    
    -- Engagement
    last_order_at TIMESTAMP,
    last_activity_at TIMESTAMP,
    
    -- Segmentation
    -- acquisition_source: Where customer came from (organic, paid, referral, etc.)
    acquisition_source VARCHAR(50),
    
    -- Marketing opt-in
    email_opt_in BOOLEAN DEFAULT FALSE,
    sms_opt_in BOOLEAN DEFAULT FALSE,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active',
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint: email unique per merchant
    CONSTRAINT customers_merchant_email_unique UNIQUE (merchant_id, email)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_customers_merchant_id ON customers(merchant_id);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_tier ON customers(merchant_id, tier);
CREATE INDEX IF NOT EXISTS idx_customers_ltv ON customers(merchant_id, ltv DESC);
CREATE INDEX IF NOT EXISTS idx_customers_last_order ON customers(merchant_id, last_order_at DESC);

-- Comments
COMMENT ON TABLE customers IS 'Customer records for each merchant';
COMMENT ON COLUMN customers.tier IS 'Customer tier based on LTV: bronze (<$250), silver ($250-$1K), gold ($1K-$5K), platinum ($5K+)';
COMMENT ON COLUMN customers.ltv IS 'Lifetime value: sum of all order totals';
