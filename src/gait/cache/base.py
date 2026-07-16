"""Abstract cache interface."""
from __future__ import annotations

MODULE_STATUS = "UNUSED"
# Part of the gait.cache package — see gait/cache/__init__.py for why this
# exists and what activating it would take.

from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CacheConfig(BaseModel):
    """Cache configuration."""
    default_ttl_seconds: int = 3600  # 1 hour default
    max_ttl_seconds: int = 86400  # 24 hour max
    namespace: str = "gait"


class Cache(ABC, Generic[T]):
    """Abstract cache interface."""

    @abstractmethod
    def get(self, key: str) -> Optional[T]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        pass

    @abstractmethod
    def set(
        self,
        key: str,
        value: T,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (None = use default)

        Returns:
            True if set successfully, False otherwise
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if key not found
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        pass

    @abstractmethod
    def clear(self) -> bool:
        """Clear all cached values.

        Returns:
            True if cleared successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key in seconds.

        Args:
            key: Cache key

        Returns:
            TTL in seconds (-1 if no expiry, -2 if not found)
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close cache connection."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
