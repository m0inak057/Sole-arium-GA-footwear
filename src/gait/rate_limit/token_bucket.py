"""Token bucket rate limiter implementation."""
from __future__ import annotations

import time
from typing import Optional

import redis

from gait.common.logging_utils import get_logger
from gait.rate_limit.base import RateLimitConfig, RateLimitError, RateLimiter

logger = get_logger(__name__)


class TokenBucketLimiter(RateLimiter):
    """Token bucket rate limiter using Redis."""

    def __init__(
        self,
        config: RateLimitConfig,
        redis_client: redis.Redis,
        namespace: str = "ratelimit",
    ):
        """Initialize token bucket rate limiter.

        Args:
            config: Rate limit configuration
            redis_client: Redis client for state storage
            namespace: Redis key namespace
        """
        self.config = config
        self.redis = redis_client
        self.namespace = namespace
        self.refill_rate = config.requests_per_period / config.period_seconds

    def _make_key(self, identifier: str) -> tuple[str, str]:
        """Create Redis keys for rate limit state.

        Args:
            identifier: Unique identifier

        Returns:
            Tuple of (tokens_key, last_refill_key)
        """
        tokens_key = f"{self.namespace}:tokens:{identifier}"
        refill_key = f"{self.namespace}:refill:{identifier}"
        return tokens_key, refill_key

    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed using token bucket.

        Args:
            identifier: Unique identifier

        Returns:
            True if request allowed, False otherwise

        Raises:
            RateLimitError: If rate limit exceeded
        """
        try:
            tokens_key, refill_key = self._make_key(identifier)
            now = time.time()

            # Get current state
            current_tokens = float(self.redis.get(tokens_key) or 0)
            last_refill = float(self.redis.get(refill_key) or now)

            # Calculate elapsed time and new tokens
            elapsed = now - last_refill
            new_tokens = current_tokens + (elapsed * self.refill_rate)

            # Cap at burst size
            tokens_to_use = min(new_tokens, self.config.burst_size)

            # Check if request allowed
            if tokens_to_use >= 1:
                # Consume one token
                remaining = tokens_to_use - 1
                self.redis.set(tokens_key, str(remaining), ex=self.config.period_seconds)
                self.redis.set(refill_key, str(now), ex=self.config.period_seconds)

                logger.debug(
                    "ratelimit.allowed",
                    extra={"identifier": identifier, "remaining": int(remaining)},
                )
                return True
            else:
                # Rate limit exceeded
                retry_after = int(1 / self.refill_rate) if self.refill_rate > 0 else 1
                logger.warning(
                    "ratelimit.exceeded",
                    extra={"identifier": identifier, "retry_after": retry_after},
                )
                raise RateLimitError(
                    f"Rate limit exceeded for {identifier}",
                    retry_after,
                )

        except redis.RedisError as e:
            logger.error("ratelimit.check_failed", extra={"error": str(e)})
            # Fail open: allow request if Redis is down
            return True

    def get_remaining(self, identifier: str) -> int:
        """Get remaining tokens for identifier.

        Args:
            identifier: Unique identifier

        Returns:
            Number of remaining tokens (0 if exhausted)
        """
        try:
            tokens_key, refill_key = self._make_key(identifier)
            now = time.time()

            current_tokens = float(self.redis.get(tokens_key) or 0)
            last_refill = float(self.redis.get(refill_key) or now)

            elapsed = now - last_refill
            new_tokens = current_tokens + (elapsed * self.refill_rate)
            remaining = int(min(new_tokens, self.config.burst_size))

            return max(0, remaining)

        except redis.RedisError:
            return 0

    def get_reset_time(self, identifier: str) -> int:
        """Get Unix timestamp when limit resets.

        Args:
            identifier: Unique identifier

        Returns:
            Unix timestamp of next reset
        """
        try:
            tokens_key, refill_key = self._make_key(identifier)
            ttl = self.redis.ttl(tokens_key)

            if ttl == -2:  # Key not found
                return int(time.time()) + self.config.period_seconds
            elif ttl == -1:  # Key exists but no expiry (shouldn't happen)
                return int(time.time()) + self.config.period_seconds
            else:
                return int(time.time()) + ttl

        except redis.RedisError:
            return int(time.time()) + self.config.period_seconds

    def reset(self, identifier: str) -> bool:
        """Reset rate limit for identifier.

        Args:
            identifier: Unique identifier

        Returns:
            True if reset successful
        """
        try:
            tokens_key, refill_key = self._make_key(identifier)
            self.redis.delete(tokens_key, refill_key)
            logger.info("ratelimit.reset", extra={"identifier": identifier})
            return True

        except redis.RedisError as e:
            logger.error("ratelimit.reset_failed", extra={"error": str(e)})
            return False

    def close(self) -> None:
        """Close rate limiter (no-op for Redis client)."""
        logger.info("ratelimit.closed")

