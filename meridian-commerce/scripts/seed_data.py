#!/usr/bin/env python3
"""
seed_data.py - Seed database with sample data for development.

Creates:
- Sample merchants (with various tiers)
- Sample customers (with different segments)
- Sample products
- Sample orders

Usage: python scripts/seed_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)

# Sample data
MERCHANT_NAMES = [
    ("Acme Electronics", "electronics"),
    ("Fashion Forward", "apparel"),
    ("Home Essentials", "home_garden"),
    ("Beauty Boutique", "beauty"),
    ("Sports Zone", "sports_outdoors"),
]

PRODUCT_NAMES = {
    "electronics": [
        "Wireless Headphones", "Smart Watch", "Bluetooth Speaker",
        "USB-C Hub", "Portable Charger", "Webcam HD", "Mechanical Keyboard",
    ],
    "apparel": [
        "Cotton T-Shirt", "Slim Fit Jeans", "Wool Sweater",
        "Running Shoes", "Leather Belt", "Casual Blazer",
    ],
    "home_garden": [
        "Plant Pot Set", "LED Desk Lamp", "Throw Blanket",
        "Kitchen Scale", "Storage Basket", "Wall Clock",
    ],
    "beauty": [
        "Face Moisturizer", "Lipstick Set", "Hair Serum",
        "Nail Polish Collection", "Perfume", "Makeup Brush Kit",
    ],
    "sports_outdoors": [
        "Yoga Mat", "Resistance Bands", "Water Bottle",
        "Hiking Backpack", "Fitness Tracker", "Camping Tent",
    ],
}

FIRST_NAMES = ["James", "Emma", "Liam", "Olivia", "Noah", "Ava", "William", "Sophia"]
LAST_NAMES = ["Smith", "Johnson", "Brown", "Taylor", "Anderson", "Thomas", "Jackson"]


def generate_id(prefix: str) -> str:
    """Generate prefixed ID."""
    return f"{prefix}_{uuid4().hex[:12]}"


def random_date(start_days_ago: int = 365) -> datetime:
    """Generate random date within range."""
    days_ago = random.randint(0, start_days_ago)
    return datetime.utcnow() - timedelta(days=days_ago)


async def create_merchants() -> list[dict]:
    """Create sample merchants."""
    merchants = []
    
    for name, industry in MERCHANT_NAMES:
        # Assign random tier based on "GMV"
        gmv = random.uniform(50000, 5000000)
        
        if gmv >= 2000000:
            tier = "platinum"
        elif gmv >= 500000:
            tier = "gold"
        elif gmv >= 100000:
            tier = "silver"
        else:
            tier = "bronze"
        
        merchant = {
            "id": generate_id("merch"),
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "tier": tier,
            "industry": industry,
            "status": "active",
            "contact_email": f"admin@{name.lower().replace(' ', '')}.com",
            "gmv_mtd": Decimal(str(round(gmv / 12, 2))),
            "gmv_12m": Decimal(str(round(gmv, 2))),
            "created_at": random_date(730),
        }
        
        merchants.append(merchant)
        logger.info("Created merchant", name=name, tier=tier)
    
    return merchants


async def create_products(merchants: list[dict]) -> list[dict]:
    """Create sample products for each merchant."""
    products = []
    
    for merchant in merchants:
        industry = merchant["industry"]
        product_list = PRODUCT_NAMES.get(industry, PRODUCT_NAMES["electronics"])
        
        for product_name in product_list:
            price = Decimal(str(round(random.uniform(19.99, 299.99), 2)))
            
            product = {
                "id": generate_id("prod"),
                "merchant_id": merchant["id"],
                "name": product_name,
                "slug": product_name.lower().replace(" ", "-"),
                "sku": f"SKU-{uuid4().hex[:8].upper()}",
                "price": price,
                "status": "active",
                "inventory_quantity": random.randint(10, 500),
                "category_path": f"{industry.replace('_', ' ').title()} > General",
                "created_at": random_date(365),
            }
            
            products.append(product)
        
        logger.info(
            "Created products for merchant",
            merchant=merchant["name"],
            count=len(product_list),
        )
    
    return products


async def create_customers(merchants: list[dict]) -> list[dict]:
    """Create sample customers for each merchant."""
    customers = []
    
    for merchant in merchants:
        num_customers = random.randint(50, 200)
        
        for _ in range(num_customers):
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            
            # Random LTV determines tier
            ltv = Decimal(str(round(random.uniform(10, 10000), 2)))
            
            if ltv >= 5000:
                tier = "platinum"
            elif ltv >= 1000:
                tier = "gold"
            elif ltv >= 250:
                tier = "silver"
            else:
                tier = "bronze"
            
            customer = {
                "id": generate_id("cust"),
                "merchant_id": merchant["id"],
                "email": f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@example.com",
                "first_name": first_name,
                "last_name": last_name,
                "tier": tier,
                "ltv": ltv,
                "total_orders": random.randint(1, 50),
                "created_at": random_date(365),
            }
            
            customers.append(customer)
        
        logger.info(
            "Created customers for merchant",
            merchant=merchant["name"],
            count=num_customers,
        )
    
    return customers


async def create_orders(
    merchants: list[dict],
    customers: list[dict],
    products: list[dict],
) -> list[dict]:
    """Create sample orders."""
    orders = []
    
    # Group customers and products by merchant
    customers_by_merchant = {}
    products_by_merchant = {}
    
    for c in customers:
        customers_by_merchant.setdefault(c["merchant_id"], []).append(c)
    
    for p in products:
        products_by_merchant.setdefault(p["merchant_id"], []).append(p)
    
    for merchant in merchants:
        merchant_customers = customers_by_merchant.get(merchant["id"], [])
        merchant_products = products_by_merchant.get(merchant["id"], [])
        
        if not merchant_customers or not merchant_products:
            continue
        
        num_orders = random.randint(100, 500)
        
        for _ in range(num_orders):
            customer = random.choice(merchant_customers)
            product = random.choice(merchant_products)
            
            quantity = random.randint(1, 3)
            subtotal = product["price"] * quantity
            tax = subtotal * Decimal("0.08")
            shipping = Decimal("5.99") if subtotal < 50 else Decimal("0")
            total = subtotal + tax + shipping
            
            order = {
                "id": generate_id("order"),
                "merchant_id": merchant["id"],
                "customer_id": customer["id"],
                "status": random.choice(["delivered", "shipped", "processing", "confirmed"]),
                "subtotal": subtotal,
                "tax_amount": tax.quantize(Decimal("0.01")),
                "shipping_amount": shipping,
                "total_amount": total.quantize(Decimal("0.01")),
                "item_count": quantity,
                "created_at": random_date(90),
            }
            
            orders.append(order)
        
        logger.info(
            "Created orders for merchant",
            merchant=merchant["name"],
            count=num_orders,
        )
    
    return orders


async def main():
    """Run seed data generation."""
    logger.info("Starting seed data generation")
    
    # Create data
    merchants = await create_merchants()
    products = await create_products(merchants)
    customers = await create_customers(merchants)
    orders = await create_orders(merchants, customers, products)
    
    # Summary
    logger.info(
        "Seed data generation complete",
        merchants=len(merchants),
        products=len(products),
        customers=len(customers),
        orders=len(orders),
    )
    
    # In production, would insert into database
    # For now, just print summary
    print(f"\n=== Seed Data Summary ===")
    print(f"Merchants: {len(merchants)}")
    print(f"Products: {len(products)}")
    print(f"Customers: {len(customers)}")
    print(f"Orders: {len(orders)}")


if __name__ == "__main__":
    asyncio.run(main())
