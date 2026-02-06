-- Promotions table definition
--
-- Promotional campaigns and discount rules for merchants.
-- Supports various discount types and targeting rules.
--
-- Discount Types:
--   - percentage: X% off (e.g., 20% off)
--   - fixed_amount: $X off (e.g., $10 off)
--   - free_shipping: Waive shipping costs
--   - buy_x_get_y: Buy X items, get Y free/discounted
--   - tiered: Different discount at different spend levels
--
-- Stacking Rules:
--   - Promotions can be exclusive (only one applies)
--   - Or stackable (combines with other promos)
--   - Priority determines which applies first
--
-- Owner: Marketing Team
-- Related: orders, coupons, order_items

CREATE TABLE IF NOT EXISTS promotions (
    -- Primary key with 'promo_' prefix
    id VARCHAR(20) PRIMARY KEY,
    
    -- Foreign key to merchant
    merchant_id VARCHAR(18) NOT NULL REFERENCES merchants(id),
    
    -- Promotion details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    internal_notes TEXT,  -- Notes for merchant staff
    
    -- Discount configuration
    discount_type VARCHAR(20) NOT NULL 
        CHECK (discount_type IN ('percentage', 'fixed_amount', 'free_shipping', 'buy_x_get_y', 'tiered')),
    
    -- Discount value (interpretation depends on discount_type)
    -- percentage: 0.20 = 20% off
    -- fixed_amount: 10.00 = $10 off
    discount_value DECIMAL(10, 2) NOT NULL,
    
    -- Maximum discount (caps large orders for percentage discounts)
    max_discount_amount DECIMAL(10, 2),
    
    -- For buy_x_get_y type
    buy_quantity INTEGER,  -- Buy this many
    get_quantity INTEGER,  -- Get this many free/discounted
    get_discount_percent DECIMAL(5, 2) DEFAULT 100,  -- 100 = free, 50 = half off
    
    -- For tiered discounts (JSONB array)
    -- Example: [{"min_spend": 50, "discount": 10}, {"min_spend": 100, "discount": 25}]
    tier_config JSONB,
    
    -- Eligibility rules
    -- minimum_order_value: Minimum subtotal to qualify
    -- minimum_quantity: Minimum items in cart
    minimum_order_value DECIMAL(10, 2) DEFAULT 0,
    minimum_quantity INTEGER DEFAULT 1,
    
    -- Product targeting (NULL = all products)
    -- Can target by product IDs, category, tags, etc.
    applicable_product_ids TEXT[],
    applicable_category_ids TEXT[],
    excluded_product_ids TEXT[],
    applicable_tags TEXT[],
    
    -- Customer targeting
    -- applicable_customer_tiers: ['platinum', 'gold'] = only these tiers
    -- first_order_only: TRUE = new customers only
    applicable_customer_tiers TEXT[],
    first_order_only BOOLEAN DEFAULT FALSE,
    
    -- Usage limits
    total_usage_limit INTEGER,  -- Max total uses across all customers
    per_customer_limit INTEGER DEFAULT 1,  -- Max uses per customer
    current_usage_count INTEGER DEFAULT 0,  -- Tracks total uses
    
    -- Stacking rules
    is_exclusive BOOLEAN DEFAULT FALSE,  -- If true, can't combine with other promos
    priority INTEGER DEFAULT 0,  -- Higher priority applies first
    
    -- Schedule
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP,
    
    -- Status
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'expired', 'depleted')),
    
    -- Channel restrictions
    -- NULL = all channels, otherwise only listed channels
    applicable_channels TEXT[],  -- ['web', 'mobile_web', 'ios_app']
    
    -- Analytics (updated in real-time)
    orders_with_promo INTEGER DEFAULT 0,
    total_discount_given DECIMAL(14, 2) DEFAULT 0,
    attributed_revenue DECIMAL(14, 2) DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50)  -- User who created the promotion
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_promotions_merchant_id ON promotions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_promotions_status ON promotions(merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_promotions_active ON promotions(merchant_id, starts_at, ends_at) 
    WHERE status = 'active';

-- Comments
COMMENT ON TABLE promotions IS 'Promotional campaigns and discount rules';
COMMENT ON COLUMN promotions.discount_type IS 'Type: percentage, fixed_amount, free_shipping, buy_x_get_y, tiered';
COMMENT ON COLUMN promotions.is_exclusive IS 'If true, cannot be combined with other promotions';
COMMENT ON COLUMN promotions.applicable_customer_tiers IS 'Limit to specific customer tiers, NULL = all';
