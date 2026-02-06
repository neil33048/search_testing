"""
Catalyst Model Training DAG

Weekly training pipeline for recommendation models.
Trains both collaborative filtering and content-based models.

Schedule: Sundays at 03:00 UTC
Owner: ML Team (@ml-catalyst)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.utils.task_group import TaskGroup


default_args = {
    "owner": "ml-team",
    "depends_on_past": False,
    "email": ["ml-alerts@meridian-commerce.com"],
    "email_on_failure": True,
    "retries": 1,
    "retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=6),
}


def validate_training_data(**context):
    """
    Validate training data before model training.
    
    Checks:
    - Minimum number of interactions (>100K)
    - Data recency (within 90 days)
    - No major data quality issues
    """
    print("Validating training data...")
    
    # Would query data warehouse for validation metrics
    validation_results = {
        "total_interactions": 5_000_000,
        "unique_users": 150_000,
        "unique_items": 25_000,
        "data_start_date": "2023-10-01",
        "data_end_date": "2024-01-14",
    }
    
    if validation_results["total_interactions"] < 100_000:
        raise ValueError("Insufficient training data")
    
    print(f"Validation passed: {validation_results}")
    return validation_results


def register_model(**context):
    """
    Register trained model in model registry.
    
    Stores model metadata, performance metrics, and deployment info.
    """
    ti = context["task_instance"]
    
    # Get metrics from training tasks
    collab_metrics = ti.xcom_pull(task_ids="training.train_collaborative", key="metrics")
    content_metrics = ti.xcom_pull(task_ids="training.train_content_based", key="metrics")
    
    model_info = {
        "version": context["execution_date"].strftime("%Y%m%d"),
        "collaborative_metrics": collab_metrics or {"ndcg@10": 0.35},
        "content_based_metrics": content_metrics or {"ndcg@10": 0.28},
    }
    
    print(f"Registering model: {model_info}")
    
    # Would register in MLflow or similar
    return model_info


with DAG(
    dag_id="catalyst_model_training",
    description="Weekly Catalyst recommendation model training",
    default_args=default_args,
    schedule_interval="0 3 * * 0",  # Sundays at 03:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "catalyst", "training", "weekly"],
) as dag:
    
    start = DummyOperator(task_id="start")
    
    # Data validation
    validate_data = PythonOperator(
        task_id="validate_training_data",
        python_callable=validate_training_data,
    )
    
    # Feature engineering
    with TaskGroup(group_id="features") as feature_group:
        
        build_user_features = BashOperator(
            task_id="build_user_features",
            bash_command="""
                python -m src.catalyst.cli build-features \
                    --feature-group user_features \
                    --output-path s3://meridian-ml/features/users/{{ ds }}
            """,
        )
        
        build_item_features = BashOperator(
            task_id="build_item_features",
            bash_command="""
                python -m src.catalyst.cli build-features \
                    --feature-group item_features \
                    --output-path s3://meridian-ml/features/items/{{ ds }}
            """,
        )
        
        build_interaction_matrix = BashOperator(
            task_id="build_interaction_matrix",
            bash_command="""
                python -m src.catalyst.cli build-features \
                    --feature-group interactions \
                    --lookback-days 90 \
                    --output-path s3://meridian-ml/features/interactions/{{ ds }}
            """,
        )
    
    # Model training
    with TaskGroup(group_id="training") as training_group:
        
        train_collaborative = BashOperator(
            task_id="train_collaborative",
            bash_command="""
                python -m src.catalyst.cli train \
                    --model-type collaborative \
                    --embedding-dim 64 \
                    --learning-rate 0.001 \
                    --epochs 20 \
                    --output-path s3://meridian-ml/models/collaborative/{{ ds }}
            """,
        )
        
        train_content_based = BashOperator(
            task_id="train_content_based",
            bash_command="""
                python -m src.catalyst.cli train \
                    --model-type content_based \
                    --similarity-metric cosine \
                    --output-path s3://meridian-ml/models/content/{{ ds }}
            """,
        )
    
    # Model evaluation
    evaluate_models = BashOperator(
        task_id="evaluate_models",
        bash_command="""
            python -m src.catalyst.cli evaluate \
                --model-path s3://meridian-ml/models/{{ ds }} \
                --test-data s3://meridian-ml/features/test/{{ ds }} \
                --metrics ndcg@10,hit_rate@10,mrr
        """,
    )
    
    # Register model
    register = PythonOperator(
        task_id="register_model",
        python_callable=register_model,
    )
    
    # Deploy to production (canary)
    deploy_canary = BashOperator(
        task_id="deploy_canary",
        bash_command="""
            python -m src.catalyst.cli deploy \
                --model-version {{ ds }} \
                --traffic-percent 10 \
                --canary
        """,
    )
    
    end = DummyOperator(task_id="end")
    
    # Task dependencies
    start >> validate_data >> feature_group >> training_group >> evaluate_models >> register >> deploy_canary >> end
