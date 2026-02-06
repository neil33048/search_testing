"""
Database connection and session management.

Provides async SQLAlchemy engine and session factory for PostgreSQL.
Supports read replicas for analytics queries (Pulse, Forge).

Usage:
    from src.core.database import get_db_session
    
    async with get_db_session() as session:
        result = await session.execute(query)
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from config.settings import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Primary engine for transactional workloads
engine = create_async_engine(
    settings.db.url,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
    echo=settings.db.echo,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,   # Recycle connections after 1 hour
)


# Read replica engine for analytics queries
# Only initialized if read replicas are configured
read_replica_engine = None
if settings.db.read_replicas:
    # Use first replica for now; could implement round-robin later
    replica_host = settings.db.read_replicas.split(",")[0].strip()
    replica_url = (
        f"postgresql+asyncpg://{settings.db.user}:{settings.db.password.get_secret_value()}"
        f"@{replica_host}/{settings.db.name}"
    )
    read_replica_engine = create_async_engine(
        replica_url,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
        echo=settings.db.echo,
        pool_pre_ping=True,
    )
    logger.info(f"Read replica engine configured: {replica_host}")


# Session factories
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Alias for compatibility with older code
DatabaseSession = AsyncSessionLocal


@asynccontextmanager
async def get_db_session(
    read_only: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session as an async context manager.
    
    Args:
        read_only: If True and read replicas are available, use replica.
                   Analytics queries (Pulse, Forge) should set this to True.
    
    Yields:
        AsyncSession: Database session
    
    Example:
        async with get_db_session() as session:
            result = await session.execute(select(Customer))
            customers = result.scalars().all()
    """
    # Use read replica for read-only queries if available
    if read_only and read_replica_engine:
        session_factory = async_sessionmaker(
            bind=read_replica_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    else:
        session_factory = AsyncSessionLocal
    
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_database_connection() -> bool:
    """
    Verify database connectivity.
    
    Used by health check endpoint.
    
    Returns:
        True if database is accessible, False otherwise
    """
    try:
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def init_database() -> None:
    """
    Initialize database schema.
    
    Creates all tables defined by SQLAlchemy models.
    Should only be used for development/testing - production uses Alembic.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized")


async def close_database() -> None:
    """
    Close database connections.
    
    Should be called during application shutdown.
    """
    await engine.dispose()
    if read_replica_engine:
        await read_replica_engine.dispose()
    logger.info("Database connections closed")


# Event listeners for connection pool monitoring
@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Log new database connections."""
    logger.debug("New database connection established")


@event.listens_for(engine.sync_engine, "checkout")
def on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log connection checkouts from pool."""
    logger.debug("Database connection checked out from pool")


# Query execution hooks for performance monitoring
# These are used by Pulse for query timing metrics
class QueryTimer:
    """
    Context manager for timing database queries.
    
    Used internally for performance monitoring and alerting
    on slow queries (>100ms).
    """
    
    def __init__(self, query_name: str = ""):
        self.query_name = query_name
        self.start_time = None
    
    async def __aenter__(self):
        import time
        self.start_time = time.perf_counter()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        import time
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        
        if duration_ms > 100:
            logger.warning(
                f"Slow query detected: {self.query_name} took {duration_ms:.2f}ms"
            )
        else:
            logger.debug(f"Query {self.query_name}: {duration_ms:.2f}ms")
