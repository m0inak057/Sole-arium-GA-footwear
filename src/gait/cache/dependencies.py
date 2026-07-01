"""Cache dependencies for FastAPI."""
from __future__ import annotations

from typing import Optional

from gait.cache.base import Cache, CacheConfig
from gait.cache.redis_cache import RedisCache


def create_redis_cache(
    config: Optional[CacheConfig] = None,
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
) -> Cache:
    """Factory function to create Redis cache.

    Args:
        config: Cache configuration (uses defaults if None)
        host: Redis host
        port: Redis port
        db: Redis database number

    Returns:
        Configured RedisCache instance

    Raises:
        redis.ConnectionError: If cannot connect to Redis
    """
    if config is None:
        config = CacheConfig()

    return RedisCache(config=config, host=host, port=port, db=db)

