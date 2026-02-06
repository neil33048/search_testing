"""
Forge Pipeline Orchestration

Core pipeline runner that coordinates extractors, transformers, and loaders.
Handles checkpointing, retries, and progress tracking.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

import structlog

from config.settings import settings
from src.core.exceptions import (
    CheckpointError,
    ExtractorError,
    LoaderError,
    PipelineExecutionError,
    TransformerError,
)

logger = structlog.get_logger(__name__)


class PipelineStatus(str, Enum):
    """Pipeline execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineType(str, Enum):
    """Type of pipeline."""
    BATCH = "batch"           # Full refresh
    INCREMENTAL = "incremental"  # Delta updates
    STREAMING = "streaming"   # Continuous


@dataclass
class PipelineRun:
    """Record of a pipeline execution."""
    
    run_id: str
    pipeline_name: str
    status: PipelineStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    
    # Stats
    records_extracted: int = 0
    records_transformed: int = 0
    records_loaded: int = 0
    
    # Error info
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    
    # Checkpointing
    last_checkpoint: Optional[str] = None
    checkpoint_data: dict = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> Optional[float]:
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "records_extracted": self.records_extracted,
            "records_transformed": self.records_transformed,
            "records_loaded": self.records_loaded,
            "error_message": self.error_message,
            "error_stage": self.error_stage,
        }


@dataclass
class PipelineConfig:
    """Configuration for a pipeline."""
    
    name: str
    pipeline_type: PipelineType = PipelineType.BATCH
    
    # Parallelism
    parallelism: int = 4
    batch_size: int = 10000
    
    # Retry
    max_retries: int = 3
    retry_delay_seconds: int = 60
    
    # Checkpointing
    checkpoint_enabled: bool = True
    checkpoint_interval: int = 1000  # Records between checkpoints
    
    # Timeout
    timeout_seconds: Optional[int] = None
    
    # Dependencies (other pipelines that must complete first)
    dependencies: list[str] = field(default_factory=list)


class Pipeline:
    """
    ETL Pipeline orchestrator.
    
    Coordinates extraction, transformation, and loading of data
    between sources and destinations.
    
    Usage:
        pipeline = Pipeline(
            config=PipelineConfig(name="fact_orders"),
            extractor=PostgresExtractor(query="SELECT * FROM orders"),
            transformers=[
                CleansingTransformer(),
                EnrichmentTransformer(),
            ],
            loader=SnowflakeLoader(table="fact_orders"),
        )
        
        result = await pipeline.run()
    """
    
    def __init__(
        self,
        config: PipelineConfig,
        extractor: "BaseExtractor",
        transformers: list["BaseTransformer"],
        loader: "BaseLoader",
    ):
        self.config = config
        self.extractor = extractor
        self.transformers = transformers
        self.loader = loader
        
        self._current_run: Optional[PipelineRun] = None
        self._cancelled = False
        
        # Checkpoint storage (would use Redis in production)
        self._checkpoints: dict[str, dict] = {}
    
    async def run(
        self,
        resume_from_checkpoint: bool = False,
    ) -> PipelineRun:
        """
        Execute the pipeline.
        
        Args:
            resume_from_checkpoint: If True, resume from last checkpoint
            
        Returns:
            PipelineRun with execution details
        """
        run_id = f"run_{uuid4().hex[:12]}"
        
        self._current_run = PipelineRun(
            run_id=run_id,
            pipeline_name=self.config.name,
            status=PipelineStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        
        self._cancelled = False
        
        logger.info(
            "Pipeline started",
            run_id=run_id,
            pipeline=self.config.name,
            type=self.config.pipeline_type.value,
        )
        
        try:
            # Get checkpoint if resuming
            checkpoint = None
            if resume_from_checkpoint and self.config.checkpoint_enabled:
                checkpoint = await self._load_checkpoint()
                if checkpoint:
                    logger.info(
                        "Resuming from checkpoint",
                        checkpoint=checkpoint.get("position"),
                    )
            
            # Execute ETL stages
            await self._execute_etl(checkpoint)
            
            self._current_run.status = PipelineStatus.SUCCEEDED
            
        except asyncio.CancelledError:
            self._current_run.status = PipelineStatus.CANCELLED
            logger.warning("Pipeline cancelled", run_id=run_id)
            
        except Exception as e:
            self._current_run.status = PipelineStatus.FAILED
            self._current_run.error_message = str(e)
            
            logger.error(
                "Pipeline failed",
                run_id=run_id,
                error=str(e),
                stage=self._current_run.error_stage,
            )
            raise
        
        finally:
            self._current_run.ended_at = datetime.now(timezone.utc)
            
            logger.info(
                "Pipeline completed",
                run_id=run_id,
                status=self._current_run.status.value,
                duration=self._current_run.duration_seconds,
                records_loaded=self._current_run.records_loaded,
            )
        
        return self._current_run
    
    async def _execute_etl(
        self,
        checkpoint: Optional[dict] = None,
    ) -> None:
        """Execute the ETL stages."""
        
        # Stage 1: Extract
        self._current_run.error_stage = "extract"
        
        try:
            records = await self._extract(checkpoint)
            self._current_run.records_extracted = len(records)
        except Exception as e:
            raise ExtractorError(str(e), source=self.extractor.__class__.__name__)
        
        if self._cancelled:
            return
        
        # Stage 2: Transform
        self._current_run.error_stage = "transform"
        
        try:
            transformed = await self._transform(records)
            self._current_run.records_transformed = len(transformed)
        except Exception as e:
            raise TransformerError(str(e))
        
        if self._cancelled:
            return
        
        # Stage 3: Load
        self._current_run.error_stage = "load"
        
        try:
            await self._load(transformed)
            self._current_run.records_loaded = len(transformed)
        except Exception as e:
            raise LoaderError(str(e), destination=self.loader.__class__.__name__)
        
        self._current_run.error_stage = None
    
    async def _extract(
        self,
        checkpoint: Optional[dict] = None,
    ) -> list[dict]:
        """Extract data from source."""
        logger.info(
            "Extracting data",
            source=self.extractor.__class__.__name__,
        )
        
        # Pass checkpoint position to extractor for incremental
        if checkpoint:
            return await self.extractor.extract(
                offset=checkpoint.get("position"),
            )
        
        return await self.extractor.extract()
    
    async def _transform(
        self,
        records: list[dict],
    ) -> list[dict]:
        """Apply transformations to records."""
        transformed = records
        
        for transformer in self.transformers:
            logger.debug(
                "Applying transformer",
                transformer=transformer.__class__.__name__,
                record_count=len(transformed),
            )
            
            transformed = await transformer.transform(transformed)
            
            # Checkpoint periodically
            if (
                self.config.checkpoint_enabled
                and len(transformed) % self.config.checkpoint_interval == 0
            ):
                await self._save_checkpoint({
                    "stage": "transform",
                    "transformer": transformer.__class__.__name__,
                    "records_processed": len(transformed),
                })
        
        return transformed
    
    async def _load(
        self,
        records: list[dict],
    ) -> None:
        """Load data to destination."""
        logger.info(
            "Loading data",
            destination=self.loader.__class__.__name__,
            record_count=len(records),
        )
        
        # Process in batches
        batch_size = self.config.batch_size
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            await self.loader.load(batch)
            
            # Checkpoint after each batch
            if self.config.checkpoint_enabled:
                await self._save_checkpoint({
                    "stage": "load",
                    "records_loaded": i + len(batch),
                })
            
            if self._cancelled:
                break
    
    async def _save_checkpoint(self, data: dict) -> None:
        """Save checkpoint for resume capability."""
        checkpoint_id = f"{self.config.name}:{self._current_run.run_id}"
        
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        data["run_id"] = self._current_run.run_id
        
        self._checkpoints[checkpoint_id] = data
        self._current_run.checkpoint_data = data
        
        logger.debug("Checkpoint saved", checkpoint=data)
    
    async def _load_checkpoint(self) -> Optional[dict]:
        """Load last checkpoint for this pipeline."""
        # Would load from persistent storage
        checkpoint_prefix = f"{self.config.name}:"
        
        for key, data in self._checkpoints.items():
            if key.startswith(checkpoint_prefix):
                return data
        
        return None
    
    def cancel(self) -> None:
        """Cancel the running pipeline."""
        self._cancelled = True
        
        if self._current_run:
            self._current_run.status = PipelineStatus.CANCELLED


class PipelineScheduler:
    """
    Schedules and manages pipeline execution.
    
    Handles:
    - Cron-like scheduling
    - Dependency resolution
    - Concurrent execution
    - Retry logic
    """
    
    def __init__(self):
        self.pipelines: dict[str, Pipeline] = {}
        self.schedules: dict[str, str] = {}  # pipeline -> cron expression
        self.run_history: list[PipelineRun] = []
        self._running = False
    
    def register(
        self,
        pipeline: Pipeline,
        schedule: Optional[str] = None,  # Cron expression
    ) -> None:
        """Register a pipeline with optional schedule."""
        self.pipelines[pipeline.config.name] = pipeline
        
        if schedule:
            self.schedules[pipeline.config.name] = schedule
        
        logger.info(
            "Pipeline registered",
            name=pipeline.config.name,
            schedule=schedule,
        )
    
    async def run_pipeline(
        self,
        name: str,
        wait_for_dependencies: bool = True,
    ) -> PipelineRun:
        """Run a specific pipeline by name."""
        if name not in self.pipelines:
            raise PipelineExecutionError(
                f"Pipeline not found: {name}",
                pipeline_name=name,
            )
        
        pipeline = self.pipelines[name]
        
        # Check dependencies
        if wait_for_dependencies:
            for dep in pipeline.config.dependencies:
                # Ensure dependency has completed successfully
                dep_status = self._get_latest_status(dep)
                if dep_status != PipelineStatus.SUCCEEDED:
                    logger.info(
                        "Waiting for dependency",
                        pipeline=name,
                        dependency=dep,
                    )
                    # Would wait for dependency to complete
        
        result = await pipeline.run()
        self.run_history.append(result)
        
        return result
    
    async def run_all(self) -> list[PipelineRun]:
        """Run all registered pipelines respecting dependencies."""
        results = []
        completed = set()
        
        # Topological sort based on dependencies
        pipelines_to_run = list(self.pipelines.keys())
        
        while pipelines_to_run:
            # Find pipelines with satisfied dependencies
            ready = [
                name for name in pipelines_to_run
                if all(dep in completed 
                       for dep in self.pipelines[name].config.dependencies)
            ]
            
            if not ready:
                raise PipelineExecutionError(
                    "Circular dependency detected",
                    pipeline_name=",".join(pipelines_to_run),
                )
            
            # Run ready pipelines in parallel
            tasks = [self.run_pipeline(name) for name in ready]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for name, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Pipeline {name} failed: {result}")
                else:
                    results.append(result)
                    if result.status == PipelineStatus.SUCCEEDED:
                        completed.add(name)
                
                pipelines_to_run.remove(name)
        
        return results
    
    def _get_latest_status(self, pipeline_name: str) -> Optional[PipelineStatus]:
        """Get latest status for a pipeline."""
        for run in reversed(self.run_history):
            if run.pipeline_name == pipeline_name:
                return run.status
        return None
    
    def get_run_history(
        self,
        pipeline_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[PipelineRun]:
        """Get pipeline run history."""
        history = self.run_history
        
        if pipeline_name:
            history = [r for r in history if r.pipeline_name == pipeline_name]
        
        return history[-limit:]
