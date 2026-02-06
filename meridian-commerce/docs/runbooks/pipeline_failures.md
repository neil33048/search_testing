# Runbook: Pipeline Failures

## Overview

This runbook covers troubleshooting and recovery for Forge data pipeline failures.

## Quick Reference

| Pipeline | Schedule | Owner | Slack Channel |
|----------|----------|-------|---------------|
| daily_etl_pipeline | 02:00 UTC | @data-forge | #data-pipeline-alerts |
| hourly_orders_sync | Every hour | @data-forge | #data-pipeline-alerts |
| catalyst_feature_update | 04:00 UTC | @ml-team | #ml-catalyst |

## Alert Types

### 1. DAG Failure

**Symptoms**: Airflow DAG marked as failed, Slack alert received

**Steps**:
1. Check Airflow UI for failed task
2. Review task logs for error details
3. Check source system connectivity
4. Retry failed task if transient error
5. If persistent, escalate to owner

### 2. dbt Model Failure

**Symptoms**: dbt run/test fails in pipeline

**Common Causes**:
- Schema changes in source tables
- Data quality issues (nulls, duplicates)
- Snowflake resource contention

**Steps**:
1. Run `dbt debug` to check connections
2. Check failed model SQL for issues
3. Review dbt test failures for data quality
4. Check Snowflake query history for errors

### 3. Extractor Failures

**Symptoms**: Extract stage fails, no data loaded

**Common Causes**:
- Database connection timeout
- Source table locked
- Network issues

**Steps**:
1. Check source database status
2. Verify credentials in Secrets Manager
3. Check for long-running queries blocking
4. Retry with increased timeout

### 4. Loader Failures

**Symptoms**: Transform succeeds but load fails

**Common Causes**:
- Snowflake warehouse suspended
- Schema mismatch
- Disk space issues

**Steps**:
1. Check Snowflake warehouse status
2. Compare source/target schemas
3. Check for constraint violations
4. Review Snowflake error logs

## Recovery Procedures

### Backfill Missing Data

```bash
# Backfill specific date range
python -m src.forge.cli backfill \
    --pipeline daily_etl_pipeline \
    --start-date 2024-01-10 \
    --end-date 2024-01-15
```

### Manual Pipeline Run

```bash
# Trigger pipeline manually
python -m src.forge.cli run-pipeline \
    --pipeline daily_etl_pipeline \
    --date 2024-01-15
```

### Resume from Checkpoint

```bash
# Resume failed pipeline from checkpoint
python -m src.forge.cli resume \
    --run-id run_abc123def456
```

## Customer Tier Impact

Pipeline failures can affect merchant tier calculations.

**GMV Calculation**: Uses `agg_daily_gmv` table
- If stale > 24 hours, manual refresh required
- Tier changes should not be applied until data is current

**Customer LTV**: Uses `dim_customers` table
- LTV calculation affects customer tier
- 12-month rolling window, so short delays acceptable

## Escalation

1. **L1 (On-Call)**: Retry, check logs, basic troubleshooting
2. **L2 (Data Engineering)**: Complex failures, schema issues
3. **L3 (Platform)**: Infrastructure, Snowflake issues

## Post-Incident

1. Document root cause
2. Update runbook if new failure mode
3. Create Jira ticket for permanent fix
4. Review monitoring coverage
