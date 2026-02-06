# Meridian Commerce Platform - Architecture

## Overview

Meridian Commerce is an enterprise e-commerce analytics platform that provides real-time insights, personalized recommendations, and event tracking for 500+ merchants.

## System Components

### 1. Beacon - Event Collection System

**Purpose**: Real-time event ingestion from merchant storefronts

**Architecture**:
- HTTP API for event ingestion
- JavaScript SDK for browser-side tracking
- Events validated against schemas
- Batched and sent to AWS Kinesis
- Processes 50M+ events/day

**Key Files**:
- `src/beacon/collector.py` - Event ingestion
- `src/beacon/validators.py` - Schema validation
- `src/beacon/schemas.py` - Event type definitions

### 2. Pulse - Real-Time Analytics Engine

**Purpose**: Powers merchant dashboard with live metrics

**Architecture**:
- ClickHouse for real-time event aggregation
- Redis for dashboard caching
- Pre-computed aggregates for common queries
- Alerting system for anomaly detection

**Key Metrics**:
- GMV (Gross Merchandise Value)
- Conversion Rate
- Average Order Value
- Sessions and Page Views

**Key Files**:
- `src/pulse/aggregator.py` - Metrics computation
- `src/pulse/dashboard.py` - Dashboard API
- `src/pulse/alerts.py` - Alerting system

### 3. Catalyst - ML Recommendation Engine

**Purpose**: Personalized product recommendations

**Architecture**:
- Collaborative filtering for users with history
- Content-based for cold start / item similarity
- Popularity as fallback
- Model serving via TensorFlow Serving

**Target Latency**: <50ms p99

**Key Files**:
- `src/catalyst/predictor.py` - Real-time serving
- `src/catalyst/trainer.py` - Model training
- `src/catalyst/models/` - Model implementations

### 4. Forge - Data Pipeline Framework

**Purpose**: ETL orchestration for data warehouse

**Architecture**:
- Extractors: PostgreSQL, Snowflake, S3, Kinesis
- Transformers: Business logic, aggregation, enrichment
- Loaders: Snowflake, ClickHouse, Redis
- Airflow for scheduling

**Key Pipelines**:
- `fact_orders` - Order transactions
- `dim_customers` - Customer dimension with LTV
- `agg_daily_gmv` - Daily GMV aggregates

**Key Files**:
- `src/forge/pipeline.py` - Pipeline orchestration
- `pipelines/dbt/` - dbt transformations
- `pipelines/airflow/dags/` - DAG definitions

## Data Architecture

### Source Systems
- **PostgreSQL**: Transactional data (orders, customers, products)
- **ClickHouse**: Event data (Beacon events)

### Data Warehouse (Snowflake)
- **Staging**: Raw data landing
- **Intermediate**: Business transformations
- **Marts**: Dimensional models for analytics

### Key Tables

| Table | Description | Update Frequency |
|-------|-------------|------------------|
| fact_orders | Order transactions | Hourly |
| fact_events | Beacon events | Real-time |
| dim_customers | Customer dimension | Daily |
| dim_products | Product catalog | Daily |
| agg_daily_gmv | GMV aggregates | Daily |

## API Architecture

### REST API (FastAPI)

**Endpoints**:
- `/api/v1/events/*` - Beacon event ingestion
- `/api/v1/analytics/*` - Pulse dashboard data
- `/api/v1/recommendations/*` - Catalyst recommendations
- `/api/v1/merchants/*` - Merchant management

**Authentication**: API keys with `mc_` prefix

**Rate Limiting**: Per-tier limits (1K-10K req/min)

## Customer Tiers

| Tier | GMV Threshold | SLA | Rate Limit |
|------|---------------|-----|------------|
| Bronze | <$100K/mo | 99.5% | 1,000/min |
| Silver | $100K-$500K/mo | 99.9% | 2,000/min |
| Gold | $500K-$2M/mo | 99.95% | 5,000/min |
| Platinum | >$2M/mo | 99.99% | 10,000/min |

> **Legacy Note**: Old systems used tier1-tier4 numbering.
> tier1 = Platinum, tier4 = Bronze

## Infrastructure

### Production Environment
- AWS ECS for application containers
- Aurora PostgreSQL for transactional DB
- ElastiCache (Redis) for caching
- ClickHouse for analytics
- Snowflake for data warehouse

### Observability
- OpenTelemetry for tracing
- Prometheus for metrics
- Grafana for dashboards
- PagerDuty for alerting

## Security

- API keys stored in AWS Secrets Manager
- All data encrypted at rest and in transit
- VPC isolation for production services
- WAF for API protection
