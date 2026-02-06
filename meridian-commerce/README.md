# Meridian Commerce Platform

[![CI](https://github.com/meridian-commerce/platform/actions/workflows/ci.yml/badge.svg)](https://github.com/meridian-commerce/platform/actions/workflows/ci.yml)
[![Deploy](https://github.com/meridian-commerce/platform/actions/workflows/deploy.yml/badge.svg)](https://github.com/meridian-commerce/platform/actions/workflows/deploy.yml)

> Enterprise e-commerce analytics platform powering real-time insights for 500+ merchants

## Overview

Meridian Commerce is our core analytics and commerce platform, serving as the backbone for merchant intelligence, customer behavior analysis, and personalized recommendations. This monorepo contains all backend services, data pipelines, and frontend components.

## Architecture

The platform consists of four main systems:

### 🔔 Beacon - Event Collection System
Real-time event ingestion and validation. Handles 50M+ events/day across all merchant storefronts. Events are collected via JavaScript SDK and server-side integrations.

### 📊 Pulse - Analytics Engine  
Real-time aggregation and dashboard serving. Powers the merchant dashboard with live GMV tracking, conversion funnels, and customer cohort analysis.

### 🚀 Catalyst - Recommendation Engine
ML-powered product recommendations using collaborative filtering and content-based models. Serves personalized recommendations at <50ms p99 latency.

### 🔧 Forge - Data Pipeline Framework
ETL orchestration for the data lakehouse. Handles nightly batch jobs, incremental syncs, and table materialization for analytics.

## Quick Start

```bash
# Clone and setup
git clone git@github.com:meridian-commerce/platform.git
cd platform

# Install dependencies
make install

# Setup local database
make db-setup

# Run development server
make dev
```

## Customer Tiers

We classify merchants into tiers based on GMV (Gross Merchandise Value):

| Tier | GMV Range | Features | SLA |
|------|-----------|----------|-----|
| Bronze | < $100K/mo | Basic analytics, Standard support | 99.5% |
| Silver | $100K - $500K/mo | + Catalyst recommendations | 99.9% |
| Gold | $500K - $2M/mo | + Custom dashboards, Priority support | 99.95% |
| Platinum | > $2M/mo | + Dedicated CSM, Custom integrations | 99.99% |

> **Legacy Note**: Some internal systems still reference `tier1-tier4` numbering. Tier1 = Platinum, Tier4 = Bronze.

## Key Metrics

- **GMV**: Gross Merchandise Value - total transaction value before returns/refunds
- **ARPU**: Average Revenue Per User - key metric for Growth team
- **CVR**: Conversion Rate - tracked per funnel stage
- **LTV**: Customer Lifetime Value - 12-month rolling calculation

## Project Structure

```
├── src/
│   ├── beacon/          # Event collection and validation
│   ├── pulse/           # Real-time analytics
│   ├── catalyst/        # Recommendation engine
│   ├── forge/           # Data pipelines
│   ├── api/             # REST API layer
│   ├── core/            # Shared infrastructure
│   ├── models/          # Domain models
│   └── utils/           # Utility functions
├── pipelines/
│   ├── sql/             # Raw SQL table definitions
│   ├── dbt/             # dbt transformations
│   └── airflow/         # DAG definitions
├── scripts/             # Operational scripts
├── tests/               # Test suites
├── docs/                # Documentation
└── frontend/            # React dashboard
```

## Development

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Node.js 20+ (for frontend)

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

See [docs/configuration.md](docs/configuration.md) for detailed variable descriptions.

### Running Tests

```bash
# Unit tests
make test-unit

# Integration tests (requires local services)
make test-integration

# Full test suite with coverage
make test-all
```

## Data Pipeline

The Forge pipeline runs nightly at 02:00 UTC. Key tables:

- `fact_orders` - Order-level transactions
- `fact_events` - Beacon event data (partitioned by date)
- `dim_customers` - Customer dimension with tier classification
- `dim_products` - Product catalog with category hierarchy
- `agg_daily_gmv` - Daily GMV aggregates by merchant

See [pipelines/README.md](pipelines/README.md) for pipeline documentation.

## Deployment

### Staging
Automatically deployed on merge to `develop` branch.

### Production
Requires approval from Platform team. Deploy via:

```bash
make deploy-prod
```

## Team Ownership

| Component | Team | Slack Channel |
|-----------|------|---------------|
| Beacon | Platform | #platform-beacon |
| Pulse | Data Engineering | #data-pulse |
| Catalyst | ML/Analytics | #ml-catalyst |
| Forge | Data Engineering | #data-forge |
| API | Platform | #platform-api |
| Frontend | Growth | #growth-dashboard |

## Runbooks

- [Incident Response](docs/runbooks/incident_response.md)
- [Pipeline Failures](docs/runbooks/pipeline_failures.md)
- [Scaling Guide](docs/runbooks/scaling.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Proprietary - Meridian Commerce Inc. © 2024
