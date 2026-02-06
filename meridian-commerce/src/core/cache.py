"""
Redis caching layer for Meridian Commerce Platform.

Provides a unified caching interface used across all systems:
- Beacon: Event deduplication
- Pulse: Dashboard data caching
- Catalyst: Recommendation caching
- API: Response caching

The cache supports multiple serialization formats and TTL policies.
"""

import json
import logging
import pickle
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheManager:
    """
    Async Redis cache manager.
    
    Provides high-level caching operations with support for:
    - JSON and pickle serialization
    - Key prefixing for namespace isolation
    - TTL management
    - Batch operations
    
    Usage:
        cache = CacheManager()
        await cache.set("user:123", user_data, ttl=3600)
        user = await cache.get("user:123")
    """
    
    # Key prefixes for different systems
    # This prevents key collisions between components
    PREFIX_BEACON = "beacon:"
    PREFIX_PULSE = "pulse:"
    PREFIX_CATALYST = "catalyst:"
    PREFIX_SESSION = "session:"
    PREFIX_RATE_LIMIT = "ratelimit:"
    
    def __init__(
        self,
        url: Optional[str] = None,
        prefix: str = "meridian:",
        default_ttl: int = 3600,
    ):
        """
        Initialize cache manager.
        
        Args:
            url: Redis URL. Defaults to settings.redis.url
            prefix: Key prefix for all cache operations
            default_ttl: Default TTL in seconds (1 hour)
        """
        self.url = url or settings.redis.url
        self.prefix = prefix
        self.default_ttl = default_ttl
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self._client is None:
            self._pool = ConnectionPool.from_url(
                self.url,
                max_connections=settings.redis.max_connections,
                socket_timeout=settings.redis.socket_timeout,
                decode_responses=False,  # We handle decoding ourselves
            )
            self._client = redis.Redis(connection_pool=self._pool)
            logger.info("Redis connection established")
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
        logger.info("Redis connection closed")
    
    @property
    def client(self) -> redis.Redis:
        """Get Redis client, raising if not connected."""
        if self._client is None:
            raise RuntimeError("Cache not connected. Call connect() first.")
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Create full key with prefix."""
        return f"{self.prefix}{key}"
    
    async def get(
        self,
        key: str,
        default: Optional[T] = None,
    ) -> Optional[T]:
        """
        Get value from cache.
        
        Args:
            key: Cache key (prefix will be added)
            default: Value to return if key not found
            
        Returns:
            Cached value or default
        """
        try:
            full_key = self._make_key(key)
            value = await self.client.get(full_key)
            
            if value is None:
                return default
            
            # Try JSON first, fall back to pickle
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return pickle.loads(value)
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return default
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        use_pickle: bool = False,
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key (prefix will be added)
            value: Value to cache
            ttl: Time to live in seconds (uses default if not specified)
            use_pickle: Use pickle instead of JSON (for complex objects)
            
        Returns:
            True if successful
        """
        try:
            full_key = self._make_key(key)
            ttl = ttl if ttl is not None else self.default_ttl
            
            if use_pickle:
                serialized = pickle.dumps(value)
            else:
                serialized = json.dumps(value)
            
            await self.client.setex(full_key, ttl, serialized)
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            full_key = self._make_key(key)
            await self.client.delete(full_key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        full_key = self._make_key(key)
        return await self.client.exists(full_key) > 0
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        Increment a counter.
        
        Used for rate limiting and metrics.
        """
        full_key = self._make_key(key)
        return await self.client.incrby(full_key, amount)
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        full_key = self._make_key(key)
        return await self.client.expire(full_key, ttl)
    
    async def mget(self, keys: list[str]) -> dict[str, Any]:
        """
        Get multiple keys at once.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dict mapping keys to values (missing keys not included)
        """
        if not keys:
            return {}
        
        full_keys = [self._make_key(k) for k in keys]
        values = await self.client.mget(full_keys)
        
        result = {}
        for key, value in zip(keys, values):
            if value is not None:
                try:
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = pickle.loads(value)
        
        return result
    
    async def mset(
        self,
        mapping: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set multiple keys at once.
        
        Note: Redis MSET doesn't support TTL, so we use a pipeline
        with individual SETEX commands.
        """
        if not mapping:
            return True
        
        ttl = ttl if ttl is not None else self.default_ttl
        
        try:
            pipe = self.client.pipeline()
            for key, value in mapping.items():
                full_key = self._make_key(key)
                serialized = json.dumps(value)
                pipe.setex(full_key, ttl, serialized)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.
        
        WARNING: Can be slow on large datasets. Use sparingly.
        
        Args:
            pattern: Redis pattern (e.g., "user:*")
            
        Returns:
            Number of keys deleted
        """
        full_pattern = self._make_key(pattern)
        deleted = 0
        
        async for key in self.client.scan_iter(match=full_pattern, count=100):
            await self.client.delete(key)
            deleted += 1
        
        logger.info(f"Cleared {deleted} keys matching pattern: {pattern}")
        return deleted
    
    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


# Global cache instance
cache = CacheManager()


def cached(
    ttl: Union[int, timedelta] = 3600,
    key_prefix: str = "",
    key_builder: Optional[Callable[..., str]] = None,
):
    """
    Decorator for caching function results.
    
    Args:
        ttl: Cache TTL in seconds or as timedelta
        key_prefix: Prefix for cache key
        key_builder: Custom function to build cache key from args
        
    Example:
        @cached(ttl=300, key_prefix="user")
        async def get_user(user_id: str) -> User:
            return await db.get_user(user_id)
    """
    if isinstance(ttl, timedelta):
        ttl_seconds = int(ttl.total_seconds())
    else:
        ttl_seconds = ttl
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default key: function_name:arg1:arg2:kwarg1=v1
                parts = [key_prefix or func.__name__]
                parts.extend(str(a) for a in args)
                parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = ":".join(parts)
            
            # Try cache first
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl=ttl_seconds)
            logger.debug(f"Cache miss, stored: {cache_key}")
            
            return result
        
        return wrapper
    return decorator


# Specialized cache managers for different components
class PulseCacheManager(CacheManager):
    """
    Cache manager for Pulse analytics.
    
    Optimized for dashboard data with shorter TTLs
    and batch operations for metrics.
    """
    
    def __init__(self):
        super().__init__(
            prefix="meridian:pulse:",
            default_ttl=settings.pulse.dashboard_cache_ttl,
        )
    
    async def cache_dashboard_metrics(
        self,
        merchant_id: str,
        metrics: dict[str, Any],
    ) -> bool:
        """Cache dashboard metrics for a merchant."""
        key = f"dashboard:{merchant_id}"
        return await self.set(key, metrics)
    
    async def get_dashboard_metrics(
        self,
        merchant_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get cached dashboard metrics."""
        key = f"dashboard:{merchant_id}"
        return await self.get(key)


class CatalystCacheManager(CacheManager):
    """
    Cache manager for Catalyst recommendations.
    
    Handles caching of recommendations with longer TTLs
    since model predictions are expensive.
    """
    
    def __init__(self):
        super().__init__(
            prefix="meridian:catalyst:",
            default_ttl=settings.catalyst.cache_ttl,
        )
    
    async def cache_recommendations(
        self,
        user_id: str,
        product_ids: list[str],
        context: Optional[str] = None,
    ) -> bool:
        """Cache recommendations for a user."""
        key = f"recs:{user_id}"
        if context:
            key = f"{key}:{context}"
        return await self.set(key, product_ids)
    
    async def get_recommendations(
        self,
        user_id: str,
        context: Optional[str] = None,
    ) -> Optional[list[str]]:
        """Get cached recommendations."""
        key = f"recs:{user_id}"
        if context:
            key = f"{key}:{context}"
        return await self.get(key)
