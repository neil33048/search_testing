"""
Meridian Commerce Platform - Application Settings

Centralized configuration management using Pydantic Settings.
All settings are loaded from environment variables with MERIDIAN_ prefix.

Usage:
    from config.settings import settings
    
    print(settings.db_host)
    print(settings.is_production)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""
    
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_DB_")
    
    host: str = "localhost"
    port: int = 5432
    name: str = "meridian_dev"
    user: str = "meridian"
    password: SecretStr = SecretStr("meridian_dev")
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False  # SQL logging
    
    # Read replicas for analytics queries (comma-separated host:port)
    read_replicas: str = ""
    
    @property
    def url(self) -> str:
        """Construct database URL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
    
    @property
    def sync_url(self) -> str:
        """Construct synchronous database URL (for Alembic)."""
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseSettings):
    """Redis cache configuration."""
    
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_REDIS_")
    
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None
    
    # Connection pool
    max_connections: int = 100
    socket_timeout: float = 5.0
    
    @property
    def url(self) -> str:
        """Construct Redis URL."""
        if self.password:
            return f"redis://:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class BeaconSettings(BaseSettings):
    """
    Beacon event collection system configuration.
    
    Beacon handles all incoming events from merchant storefronts.
    Events are batched for efficiency before being sent to Kinesis.
    """
    
    model_config = SettingsConfigDict(env_prefix="BEACON_")
    
    batch_size: int = 1000
    flush_interval_ms: int = 5000
    max_event_size_kb: int = 100
    kinesis_stream: str = "meridian-events"
    
    # Validation settings
    strict_validation: bool = True
    allow_unknown_events: bool = False
    
    # Rate limiting per merchant
    rate_limit_per_second: int = 10000


class PulseSettings(BaseSettings):
    """
    Pulse real-time analytics configuration.
    
    Pulse powers the merchant dashboard with live metrics.
    Uses ClickHouse for real-time aggregations.
    """
    
    model_config = SettingsConfigDict(env_prefix="PULSE_")
    
    aggregation_window_seconds: int = 60
    dashboard_cache_ttl: int = 300  # 5 minutes
    realtime_enabled: bool = True
    
    # ClickHouse connection
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "pulse"


class CatalystSettings(BaseSettings):
    """
    Catalyst recommendation engine configuration.
    
    ML-powered product recommendations. Uses collaborative filtering
    as primary model with content-based fallback.
    
    Historical note: Before v2.0, this was called "Recommender" and used
    a simpler item-item similarity model. The name "Catalyst" was chosen
    during the 2023 platform rebrand.
    """
    
    model_config = SettingsConfigDict(env_prefix="CATALYST_")
    
    model_version: str = "v2.3.1"
    
    # Fallback strategy when collaborative filtering has insufficient data
    # Options: popularity, content_based, hybrid
    fallback_strategy: Literal["popularity", "content_based", "hybrid"] = "popularity"
    
    # Minimum user interactions required for collaborative filtering
    min_interactions: int = 100
    
    cache_ttl: int = 3600  # 1 hour
    
    # Model serving
    serving_endpoint: str = "http://localhost:8501"
    batch_size: int = 32
    timeout_seconds: float = 0.5  # p99 target is 50ms


class ForgeSettings(BaseSettings):
    """
    Forge data pipeline configuration.
    
    Forge orchestrates all ETL jobs including nightly batch processing
    and incremental syncs.
    """
    
    model_config = SettingsConfigDict(env_prefix="FORGE_")
    
    parallelism: int = 4
    checkpoint_enabled: bool = True
    checkpoint_interval: int = 1000
    
    # Data warehouse
    warehouse_type: Literal["snowflake", "bigquery", "postgres"] = "snowflake"
    
    # Retry configuration
    max_retries: int = 3
    retry_delay_seconds: int = 60


class CustomerTierSettings(BaseSettings):
    """
    Customer tier thresholds based on GMV.
    
    IMPORTANT: These thresholds are used for SLA calculations.
    Any changes must be approved by the Growth team.
    
    Legacy note: Old systems used tier1-tier4 numbering where tier1 = Platinum.
    The mapping is: tier1 -> Platinum, tier2 -> Gold, tier3 -> Silver, tier4 -> Bronze
    """
    
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_TIER_")
    
    # Monthly GMV thresholds (in USD)
    platinum_threshold: int = 2_000_000
    gold_threshold: int = 500_000
    silver_threshold: int = 100_000
    # Bronze = anything below silver_threshold
    
    # SLA targets (uptime percentage)
    platinum_sla: float = 99.99
    gold_sla: float = 99.95
    silver_sla: float = 99.9
    bronze_sla: float = 99.5


class Settings(BaseSettings):
    """
    Main application settings.
    
    All settings are loaded from environment variables.
    Use MERIDIAN_ prefix for main settings.
    """
    
    model_config = SettingsConfigDict(
        env_prefix="MERIDIAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Application
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    secret_key: SecretStr = SecretStr("change-me-in-production")
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_reload: bool = False
    
    # API versioning
    api_version: str = "v1"
    api_title: str = "Meridian Commerce API"
    
    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    
    # Nested settings
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    beacon: BeaconSettings = Field(default_factory=BeaconSettings)
    pulse: PulseSettings = Field(default_factory=PulseSettings)
    catalyst: CatalystSettings = Field(default_factory=CatalystSettings)
    forge: ForgeSettings = Field(default_factory=ForgeSettings)
    tiers: CustomerTierSettings = Field(default_factory=CustomerTierSettings)
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.env == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.env == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Convenience accessor
settings = get_settings()
