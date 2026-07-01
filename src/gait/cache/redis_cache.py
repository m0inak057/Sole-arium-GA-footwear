"""Redis cache implementation."""
from __future__ import annotations

import json
from typing import Any, Optional

import redis

from gait.cache.base import Cache, CacheConfig
from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


class RedisCache(Cache):
    """Redis-based cache implementation."""

    def __init__(
        self,
        config: CacheConfig,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        decode_responses: bool = True,
    ):
        """Initialize Redis cache.

        Args:
            config: Cache configuration
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            db: Redis database number (default: 0)
            decode_responses: Decode responses to strings (default: True)

        Raises:
            redis.ConnectionError: If cannot connect to Redis
        """
        self.config = config
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Test connection
            self.redis_client.ping()
            logger.info(
                "redis.connected",
                extra={"host": host, "port": port, "db": db},
            )
        except redis.ConnectionError as e:
            logger.error("redis.connection_failed", extra={"error": str(e)})
            raise

    def _make_key(self, key: str) -> str:
        """Create namespaced cache key.

        Args:
            key: Cache key

        Returns:
            Namespaced key (format: {namespace}:{key})
        """
        return f"{self.config.namespace}:{key}"

    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        try:
            full_key = self._make_key(key)
            value = self.redis_client.get(full_key)

            if value is None:
                logger.debug("cache.miss", extra={"key": key})
                return None

            # Try to parse as JSON (for complex objects)
            try:
                result = json.loads(value)
                logger.debug("cache.hit", extra={"key": key})
                return result
            except json.JSONDecodeError:
                # Return as string if not JSON
                logger.debug("cache.hit", extra={"key": key})
                return value

        except redis.RedisError as e:
            logger.error("cache.get_failed", extra={"key": key, "error": str(e)})
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Set value in Redis cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (None = use default)

        Returns:
            True if set successfully, False otherwise
        """
        try:
            full_key = self._make_key(key)
            ttl = ttl_seconds or self.config.default_ttl_seconds

            # Validate TTL
            if ttl <= 0:
                logger.warning("cache.invalid_ttl", extra={"ttl": ttl})
                return False
            if ttl > self.config.max_ttl_seconds:
                ttl = self.config.max_ttl_seconds

            # Serialize value
            if isinstance(value, str):
                serialized = value
            else:
                serialized = json.dumps(value)

            # Set in Redis with expiry
            self.redis_client.setex(full_key, ttl, serialized)
            logger.debug(
                "cache.set",
                extra={"key": key, "ttl_seconds": ttl},
            )
            return True

        except redis.RedisError as e:
            logger.error("cache.set_failed", extra={"key": key, "error": str(e)})
            return False

    def delete(self, key: str) -> bool:
        """Delete value from Redis cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if key not found
        """
        try:
            full_key = self._make_key(key)
            result = self.redis_client.delete(full_key)
            if result:
                logger.debug("cache.deleted", extra={"key": key})
            else:
                logger.debug("cache.not_found", extra={"key": key})
            return bool(result)

        except redis.RedisError as e:
            logger.error("cache.delete_failed", extra={"key": key, "error": str(e)})
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            full_key = self._make_key(key)
            return bool(self.redis_client.exists(full_key))

        except redis.RedisError as e:
            logger.error("cache.exists_failed", extra={"key": key, "error": str(e)})
            return False

    def clear(self) -> bool:
        """Clear all cached values in namespace.

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            pattern = f"{self.config.namespace}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.info("cache.cleared", extra={"count": len(keys)})
            return True

        except redis.RedisError as e:
            logger.error("cache.clear_failed", extra={"error": str(e)})
            return False

    def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key in seconds.

        Args:
            key: Cache key

        Returns:
            TTL in seconds (-1 if no expiry, -2 if not found)
        """
        try:
            full_key = self._make_key(key)
            ttl = self.redis_client.ttl(full_key)
            return ttl

        except redis.RedisError as e:
            logger.error("cache.ttl_failed", extra={"key": key, "error": str(e)})
            return -2

    def close(self) -> None:
        """Close Redis connection."""
        try:
            self.redis_client.close()
            logger.info("redis.closed")
        except Exception as e:
            logger.error("redis.close_failed", extra={"error": str(e)})

