"""
Hourly Orders Sync DAG

Syncs order data from PostgreSQL to Snowflake on an hourly basis.
This provides near real-time order data for Pulse analytics.

Schedule: Every hour at minute 15
Owner: Data Engineering (@data-forge)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.sensors.sql import SqlSensor


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email": ["data-alerts@meridian-commerce.com"],
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
}


def check_data_freshness(**context):
    """Check if source data is fresh enough to sync."""
    execution_date = context["execution_date"]
    
    # Logic to check if PostgreSQL has recent data
    # Would query max(updated_at) from orders table
    
    print(f"Checking data freshness for {execution_date}")
    return True


def log_sync_metrics(**context):
    """Log sync metrics to monitoring system."""
    ti = context["task_instance"]
    
    # Would extract metrics from previous tasks
    metrics = {
        "dag_id": "hourly_orders_sync",
        "execution_date": str(context["execution_date"]),
        "rows_synced": ti.xcom_pull(task_ids="sync_orders", key="rows_synced") or 0,
    }
    
    print(f"Sync metrics: {metrics}")


with DAG(
    dag_id="hourly_orders_sync",
    description="Hourly sync of orders from PostgreSQL to Snowflake",
    default_args=default_args,
    schedule_interval="15 * * * *",  # Every hour at :15
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sync", "hourly", "orders"],
) as dag:
    
    # Check if source has new data
    check_source = SqlSensor(
        task_id="check_source_data",
        conn_id="postgres_default",
        sql="""
            SELECT COUNT(*) > 0
            FROM orders
            WHERE updated_at >= NOW() - INTERVAL '2 hours'
        """,
        mode="poke",
        poke_interval=60,
        timeout=300,
    )
    
    # Check data freshness
    validate_freshness = PythonOperator(
        task_id="validate_freshness",
        python_callable=check_data_freshness,
    )
    
    # Extract orders
    extract_orders = BashOperator(
        task_id="extract_orders",
        bash_command="""
            python -m src.forge.cli extract \
                --source postgres \
                --table orders \
                --incremental \
                --since '{{ execution_date - macros.timedelta(hours=2) }}'
        """,
    )
    
    # Load to Snowflake
    sync_orders = BashOperator(
        task_id="sync_orders",
        bash_command="""
            python -m src.forge.cli load \
                --destination snowflake \
                --table staging.stg_orders_hourly \
                --mode upsert \
                --key-columns id
        """,
    )
    
    # Update fact table
    update_fact = BashOperator(
        task_id="update_fact_table",
        bash_command="""
            python -m src.forge.cli run-sql \
                --file pipelines/sql/update_fact_orders_hourly.sql
        """,
    )
    
    # Log metrics
    log_metrics = PythonOperator(
        task_id="log_metrics",
        python_callable=log_sync_metrics,
    )
    
    # Task dependencies
    check_source >> validate_freshness >> extract_orders >> sync_orders >> update_fact >> log_metrics
