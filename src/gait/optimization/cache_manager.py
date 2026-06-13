"""Intelligent caching for gait analysis computations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import hashlib
import pickle
import time

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    value: Any
    timestamp: float
    ttl_seconds: float
    hit_count: int = 0
    access_times: list[float] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.timestamp > self.ttl_seconds

    def record_hit(self) -> None:
        """Record cache hit."""
        self.hit_count += 1
        self.access_times.append(time.time())


@dataclass
class CacheStats:
    """Cache performance statistics."""
    total_gets: int = 0
    total_puts: int = 0
    total_hits: int = 0
    hit_rate: float = 0.0
    avg_entry_size_bytes: float = 0.0
    total_entries: int = 0


class ComputationCache:
    """In-memory cache for expensive computations."""

    def __init__(self, max_entries: int = 1000, default_ttl_seconds: float = 3600.0):
        """Initialize cache.

        Args:
            max_entries: Maximum number of entries
            default_ttl_seconds: Default time-to-live for entries
        """
        self.max_entries = max_entries
        self.default_ttl = default_ttl_seconds
        self.cache: dict[str, CacheEntry] = {}
        self.stats = CacheStats()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value, or None if not found/expired
        """
        try:
            self.stats.total_gets += 1

            if key not in self.cache:
                logger.debug("cache.miss", extra={"key": key})
                return None

            entry = self.cache[key]

            if entry.is_expired():
                del self.cache[key]
                logger.debug("cache.expired", extra={"key": key})
                return None

            entry.record_hit()
            self.stats.total_hits += 1

            logger.debug(
                "cache.hit",
                extra={"key": key, "hit_count": entry.hit_count},
            )

            return entry.value

        except Exception as e:
            logger.error("cache.get_failed", extra={"error": str(e)})
            return None

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Put value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live (uses default if None)
        """
        try:
            self.stats.total_puts += 1
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl

            # Evict oldest entry if at capacity
            if len(self.cache) >= self.max_entries:
                self._evict_oldest()

            self.cache[key] = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl_seconds=ttl,
            )

            logger.debug("cache.put", extra={"key": key, "ttl": ttl})

        except Exception as e:
            logger.error("cache.put_failed", extra={"error": str(e)})

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        logger.debug("cache.cleared")

    def compute_or_cache(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl_seconds: Optional[float] = None,
    ) -> Any:
        """Get cached value or compute and cache.

        Args:
            key: Cache key
            compute_fn: Function to compute value if not cached
            ttl_seconds: Time-to-live for new entry

        Returns:
            Cached or newly computed value
        """
        try:
            cached = self.get(key)
            if cached is not None:
                return cached

            result = compute_fn()
            self.put(key, result, ttl_seconds)
            return result

        except Exception as e:
            logger.error("cache.compute_failed", extra={"error": str(e)})
            raise

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        try:
            total_size = sum(
                len(pickle.dumps(entry.value))
                for entry in self.cache.values()
            )
            avg_size = total_size / len(self.cache) if self.cache else 0

            hit_rate = (
                self.stats.total_hits / self.stats.total_gets
                if self.stats.total_gets > 0
                else 0.0
            )

            return CacheStats(
                total_gets=self.stats.total_gets,
                total_puts=self.stats.total_puts,
                total_hits=self.stats.total_hits,
                hit_rate=hit_rate,
                avg_entry_size_bytes=avg_size,
                total_entries=len(self.cache),
            )

        except Exception as e:
            logger.error("cache.stats_failed", extra={"error": str(e)})
            return self.stats

    def _evict_oldest(self) -> None:
        """Evict oldest entry by access time."""
        try:
            # Find entry with least recent access
            oldest_key = min(
                self.cache.keys(),
                key=lambda k: (
                    self.cache[k].access_times[-1]
                    if self.cache[k].access_times
                    else self.cache[k].timestamp
                ),
            )
            del self.cache[oldest_key]
            logger.debug("cache.evicted", extra={"key": oldest_key})

        except Exception as e:
            logger.error("cache.eviction_failed", extra={"error": str(e)})


def hash_input(input_data: Any) -> str:
    """Hash input data for cache key generation.

    Args:
        input_data: Data to hash

    Returns:
        Hexadecimal hash string
    """
    try:
        serialized = pickle.dumps(input_data)
        return hashlib.sha256(serialized).hexdigest()

    except Exception:
        # Fallback for unhashable types
        return hashlib.sha256(str(input_data).encode()).hexdigest()
