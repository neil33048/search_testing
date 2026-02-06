-- Merchants table definition
--
-- Core table storing merchant account information.
-- Each merchant represents a business using the Meridian Commerce platform.
--
-- Tier System:
--   - Platinum: >$2M annual GMV, 99.99% SLA, 10K req/min
--   - Gold: $500K-$2M GMV, 99.95% SLA, 5K req/min
--   - Silver: $100K-$500K GMV, 99.9% SLA, 2K req/min  
--   - Bronze: <$100K GMV, 99.5% SLA, 1K req/min
--
-- Legacy Note: Old systems used tier1-tier4 numbering where tier1=Platinum
--
-- Owner: Platform Team
-- Related: orders, customers, products, events

CREATE TABLE IF NOT EXISTS merchants (
    -- Primary key with 'merch_' prefix
    id VARCHAR(18) PRIMARY KEY,
    
    -- Business information
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    legal_name VARCHAR(255),
    
    -- Industry classification for analytics and recommendations
    -- Values: electronics, apparel, home_garden, beauty, sports_outdoors, food_beverage, health_wellness
    industry VARCHAR(50),
    
    -- Merchant tier (determines SLA, rate limits, and features)
    -- Calculated from trailing 12-month GMV
    tier VARCHAR(20) DEFAULT 'bronze' CHECK (tier IN ('bronze', 'silver', 'gold', 'platinum')),
    
    -- Account status
    -- active: Normal operation
    -- suspended: Temporarily disabled (payment issues, policy violations)
    -- churned: No activity for 90+ days
    -- pending: Awaiting activation
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('active', 'suspended', 'churned', 'pending')),
    suspension_reason VARCHAR(255),
    
    -- Contact information
    contact_email VARCHAR(255) NOT NULL,
    contact_phone VARCHAR(20),
    support_email VARCHAR(255),
    
    -- Billing address
    billing_address_line1 VARCHAR(255),
    billing_address_line2 VARCHAR(255),
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_country VARCHAR(2) DEFAULT 'US',
    
    -- Financial metrics (updated daily by GMV pipeline)
    -- GMV = Gross Merchandise Value = sum of order subtotals
    gmv_mtd DECIMAL(14, 2) DEFAULT 0,         -- Month to date
    gmv_qtd DECIMAL(14, 2) DEFAULT 0,         -- Quarter to date
    gmv_ytd DECIMAL(14, 2) DEFAULT 0,         -- Year to date
    gmv_12m DECIMAL(14, 2) DEFAULT 0,         -- Trailing 12 months (used for tier)
    
    -- Platform fees
    -- take_rate: Percentage of GMV charged as platform fee
    -- Varies by tier: Bronze 2.9%, Silver 2.5%, Gold 2.0%, Platinum 1.5%
    take_rate DECIMAL(5, 4) DEFAULT 0.0290,
    
    -- Feature flags stored as JSONB
    -- Example: {"beacon_enabled": true, "catalyst_enabled": true, "pulse_pro": false}
    feature_flags JSONB DEFAULT '{}',
    
    -- Integration settings
    -- api_version: Current API version (v1, v2)
    api_version VARCHAR(10) DEFAULT 'v1',
    webhook_url VARCHAR(500),
    webhook_secret VARCHAR(64),
    
    -- Onboarding
    onboarding_completed_at TIMESTAMP,
    first_order_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_merchants_status ON merchants(status);
CREATE INDEX IF NOT EXISTS idx_merchants_tier ON merchants(tier);
CREATE INDEX IF NOT EXISTS idx_merchants_industry ON merchants(industry);
CREATE INDEX IF NOT EXISTS idx_merchants_gmv_12m ON merchants(gmv_12m DESC);
CREATE INDEX IF NOT EXISTS idx_merchants_created_at ON merchants(created_at);

-- Comments
COMMENT ON TABLE merchants IS 'Merchant accounts on the Meridian Commerce platform';
COMMENT ON COLUMN merchants.tier IS 'Merchant tier based on 12-month GMV: bronze/silver/gold/platinum';
COMMENT ON COLUMN merchants.gmv_12m IS 'Trailing 12-month GMV used for tier calculation';
COMMENT ON COLUMN merchants.take_rate IS 'Platform fee percentage charged on GMV';
