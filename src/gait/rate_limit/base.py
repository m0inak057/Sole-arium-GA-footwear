"""Abstract rate limiter interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel


class RateLimitStrategy(str, Enum):
    """Rate limiting strategy."""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


class RateLimitConfig(BaseModel):
    """Rate limit configuration."""
    requests_per_period: int  # Max requests in period
    period_seconds: int  # Time period in seconds
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
    burst_size: int = 10  # Max burst size (for token bucket)


class RateLimitError(Exception):
    """Rate limit exceeded error."""

    def __init__(self, message: str, retry_after_seconds: int):
        """Initialize rate limit error.

        Args:
            message: Error message
            retry_after_seconds: Seconds to wait before retry
        """
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class RateLimiter(ABC):
    """Abstract rate limiter interface."""

    @abstractmethod
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed for identifier.

        Args:
            identifier: Unique identifier (user ID, IP, API key, etc.)

        Returns:
            True if request allowed, False if rate limit exceeded

        Raises:
            RateLimitError: If rate limit exceeded (includes retry_after)
        """
        pass

    @abstractmethod
    def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for identifier in current period.

        Args:
            identifier: Unique identifier

        Returns:
            Number of remaining requests (0 if exhausted)
        """
        pass

    @abstractmethod
    def get_reset_time(self, identifier: str) -> int:
        """Get Unix timestamp when limit resets.

        Args:
            identifier: Unique identifier

        Returns:
            Unix timestamp of next reset
        """
        pass

    @abstractmethod
    def reset(self, identifier: str) -> bool:
        """Reset rate limit for identifier.

        Args:
            identifier: Unique identifier

        Returns:
            True if reset successful, False otherwise
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close rate limiter resources."""
        pass
