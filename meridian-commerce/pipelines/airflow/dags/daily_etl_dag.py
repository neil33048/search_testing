"""
Daily ETL DAG

Orchestrates nightly data pipeline runs for the Meridian Commerce platform.
Runs at 02:00 UTC daily.

Pipeline order:
1. Extract from transactional database
2. Run dbt models (staging -> intermediate -> marts)
3. Update aggregates
4. Refresh Catalyst model features
5. Warm Pulse caches

Owner: Data Engineering (@data-forge)
Slack: #data-pipeline-alerts
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.utils.task_group import TaskGroup

# Default arguments for all tasks
default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email": ["data-alerts@meridian-commerce.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def notify_slack_on_failure(context):
    """Send Slack notification on task failure."""
    # Would use Slack webhook
    task = context.get("task_instance")
    dag = context.get("dag")
    
    message = f"""
    :red_circle: DAG Task Failed
    
    *DAG*: {dag.dag_id}
    *Task*: {task.task_id}
    *Execution Date*: {context.get("execution_date")}
    *Log URL*: {task.log_url}
    """
    
    print(f"Would send to Slack: {message}")


def notify_slack_on_success(context):
    """Send Slack notification on DAG success."""
    dag = context.get("dag")
    
    message = f"""
    :white_check_mark: DAG Completed Successfully
    
    *DAG*: {dag.dag_id}
    *Execution Date*: {context.get("execution_date")}
    """
    
    print(f"Would send to Slack: {message}")


# DAG Definition
with DAG(
    dag_id="daily_etl_pipeline",
    description="Daily ETL pipeline for Meridian Commerce analytics",
    default_args=default_args,
    schedule_interval="0 2 * * *",  # 02:00 UTC daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["etl", "daily", "core"],
    on_failure_callback=notify_slack_on_failure,
) as dag:
    
    # Start marker
    start = DummyOperator(task_id="start")
    
    # ==========================================================================
    # Stage 1: Extract data from source systems
    # ==========================================================================
    with TaskGroup(group_id="extract") as extract_group:
        
        extract_orders = BashOperator(
            task_id="extract_orders",
            bash_command="""
                python -m src.forge.cli extract \
                    --source postgres \
                    --table orders \
                    --incremental \
                    --since '{{ ds }}'
            """,
        )
        
        extract_customers = BashOperator(
            task_id="extract_customers",
            bash_command="""
                python -m src.forge.cli extract \
                    --source postgres \
                    --table customers \
                    --incremental \
                    --since '{{ ds }}'
            """,
        )
        
        extract_products = BashOperator(
            task_id="extract_products",
            bash_command="""
                python -m src.forge.cli extract \
                    --source postgres \
                    --table products \
                    --incremental \
                    --since '{{ ds }}'
            """,
        )
        
        extract_events = BashOperator(
            task_id="extract_events",
            bash_command="""
                python -m src.forge.cli extract \
                    --source clickhouse \
                    --table events \
                    --date '{{ ds }}'
            """,
        )
    
    # ==========================================================================
    # Stage 2: Run dbt transformations
    # ==========================================================================
    with TaskGroup(group_id="transform_dbt") as dbt_group:
        
        dbt_deps = BashOperator(
            task_id="dbt_deps",
            bash_command="cd pipelines/dbt && dbt deps",
        )
        
        dbt_staging = BashOperator(
            task_id="dbt_run_staging",
            bash_command="cd pipelines/dbt && dbt run --select staging",
        )
        
        dbt_intermediate = BashOperator(
            task_id="dbt_run_intermediate",
            bash_command="cd pipelines/dbt && dbt run --select intermediate",
        )
        
        dbt_marts = BashOperator(
            task_id="dbt_run_marts",
            bash_command="cd pipelines/dbt && dbt run --select marts",
        )
        
        dbt_test = BashOperator(
            task_id="dbt_test",
            bash_command="cd pipelines/dbt && dbt test",
        )
        
        dbt_deps >> dbt_staging >> dbt_intermediate >> dbt_marts >> dbt_test
    
    # ==========================================================================
    # Stage 3: Update aggregates and derived tables
    # ==========================================================================
    with TaskGroup(group_id="aggregates") as agg_group:
        
        update_daily_gmv = SnowflakeOperator(
            task_id="update_daily_gmv",
            snowflake_conn_id="snowflake_default",
            sql="""
                INSERT INTO marts.agg_daily_gmv
                SELECT * FROM marts.agg_daily_gmv_staging
                WHERE order_date = '{{ ds }}';
            """,
        )
        
        update_merchant_metrics = BashOperator(
            task_id="update_merchant_metrics",
            bash_command="""
                python -m src.forge.cli run-pipeline \
                    --pipeline merchant_metrics \
                    --date '{{ ds }}'
            """,
        )
        
        update_customer_tiers = BashOperator(
            task_id="update_customer_tiers",
            bash_command="""
                python -m src.forge.cli run-pipeline \
                    --pipeline customer_tiers \
                    --date '{{ ds }}'
            """,
        )
    
    # ==========================================================================
    # Stage 4: Update Catalyst (ML) features
    # ==========================================================================
    with TaskGroup(group_id="catalyst_features") as catalyst_group:
        
        update_user_features = BashOperator(
            task_id="update_user_features",
            bash_command="""
                python -m src.catalyst.cli update-features \
                    --feature-group user_features \
                    --date '{{ ds }}'
            """,
        )
        
        update_item_features = BashOperator(
            task_id="update_item_features",
            bash_command="""
                python -m src.catalyst.cli update-features \
                    --feature-group item_features \
                    --date '{{ ds }}'
            """,
        )
        
        update_user_features >> update_item_features
    
    # ==========================================================================
    # Stage 5: Warm caches
    # ==========================================================================
    with TaskGroup(group_id="cache_warm") as cache_group:
        
        warm_pulse_cache = BashOperator(
            task_id="warm_pulse_cache",
            bash_command="python -m src.pulse.cli warm-cache --all-merchants",
        )
        
        warm_catalyst_cache = BashOperator(
            task_id="warm_catalyst_cache",
            bash_command="python -m src.catalyst.cli warm-cache --popular-items",
        )
    
    # End marker
    end = DummyOperator(
        task_id="end",
        on_success_callback=notify_slack_on_success,
    )
    
    # ==========================================================================
    # Task Dependencies
    # ==========================================================================
    
    start >> extract_group >> dbt_group >> agg_group >> catalyst_group >> cache_group >> end
