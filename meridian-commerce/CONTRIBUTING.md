# Contributing to Meridian Commerce Platform

Thank you for contributing to the Meridian Commerce platform! This document outlines our development practices and guidelines.

## Development Workflow

### Branch Naming

Use the following conventions:
- `feature/MC-{ticket}-short-description` - New features
- `bugfix/MC-{ticket}-short-description` - Bug fixes
- `hotfix/MC-{ticket}-short-description` - Production hotfixes
- `refactor/MC-{ticket}-short-description` - Code refactoring

Example: `feature/MC-4521-add-catalyst-ab-testing`

### Commit Messages

Follow conventional commits:

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Scopes: `beacon`, `pulse`, `catalyst`, `forge`, `api`, `core`

Example:
```
feat(catalyst): add content-based filtering fallback

When collaborative filtering has insufficient data (<100 interactions),
fall back to content-based recommendations using product embeddings.

Closes MC-4521
```

### Pull Requests

1. Create PR against `develop` branch
2. Fill out the PR template completely
3. Ensure CI passes (tests, linting, type checking)
4. Request review from component owner
5. Squash and merge after approval

### Code Review Guidelines

- Respond to reviews within 24 hours
- Keep PRs focused and < 500 lines when possible
- Include tests for new functionality
- Update documentation if behavior changes

## Code Standards

### Python

- Follow PEP 8 with line length of 100
- Use type hints for all public functions
- Docstrings required for public classes and functions
- Use `ruff` for linting and formatting

```python
def calculate_customer_ltv(
    customer_id: str,
    lookback_months: int = 12,
    include_refunds: bool = True,
) -> Decimal:
    """
    Calculate customer lifetime value over a rolling window.
    
    Args:
        customer_id: The unique customer identifier (MC format: cust_xxxx)
        lookback_months: Number of months to include in calculation
        include_refunds: Whether to subtract refunded amounts
        
    Returns:
        The calculated LTV as a Decimal with 2 decimal places
        
    Raises:
        CustomerNotFoundError: If customer_id doesn't exist
    """
```

### SQL

- Use lowercase for SQL keywords (matches dbt convention)
- Use CTEs over subqueries for readability
- Include a header comment with description and owner

```sql
-- fact_orders.sql
-- Description: Order-level fact table with denormalized customer and product info
-- Owner: Data Engineering (@data-forge)
-- Schedule: Nightly at 02:00 UTC
-- Dependencies: stg_orders, dim_customers, dim_products

with orders as (
    select * from {{ ref('stg_orders') }}
),
...
```

### Testing

- Unit tests: `tests/unit/test_{module}/test_{file}.py`
- Integration tests: `tests/integration/test_{feature}.py`
- Use pytest fixtures for common setup
- Mock external services (Redis, Postgres) in unit tests
- Minimum 80% coverage for new code

## Architecture Decisions

Major architectural changes require an ADR (Architecture Decision Record). Create a new file in `docs/adr/` using the template:

```markdown
# ADR-{number}: {title}

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
Why is this decision needed?

## Decision
What is the change being proposed?

## Consequences
What are the positive and negative impacts?
```

## Component Guidelines

### Beacon Events

When adding new event types:
1. Define schema in `src/beacon/schemas.py`
2. Add validation in `src/beacon/validators.py`
3. Update event type enum in `src/beacon/event_types.py`
4. Create corresponding dbt staging model

### Pulse Metrics

New dashboard metrics require:
1. Aggregation logic in `src/pulse/aggregator.py`
2. API endpoint in `src/api/routes/analytics.py`
3. Frontend component update

### Catalyst Models

ML model changes must include:
1. Model card in `docs/models/`
2. A/B test plan
3. Rollback procedure

### Forge Pipelines

New pipelines require:
1. DAG definition in `pipelines/airflow/dags/`
2. dbt model if creating tables
3. Alerting configuration
4. Runbook for failure scenarios

## Getting Help

- **#platform-dev** - General development questions
- **#data-engineering** - Data pipeline questions
- **#ml-team** - ML/Catalyst questions
- **#oncall-platform** - Production issues

## Security

- Never commit secrets or credentials
- Use `MERIDIAN_` prefix for environment variables
- Report security issues to security@meridian-commerce.com
