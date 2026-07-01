"""Rate limiting dependencies for FastAPI."""
from __future__ import annotations

from typing import Optional

import redis

from gait.rate_limit.base import RateLimitConfig, RateLimiter, RateLimitStrategy
from gait.rate_limit.token_bucket import TokenBucketLimiter


def create_token_bucket_limiter(
    requests_per_period: int = 100,
    period_seconds: int = 60,
    burst_size: int = 10,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    namespace: str = "ratelimit",
) -> RateLimiter:
    """Factory function to create token bucket rate limiter.

    Args:
        requests_per_period: Max requests in period
        period_seconds: Period duration in seconds
        burst_size: Maximum burst size
        redis_host: Redis host
        redis_port: Redis port
        redis_db: Redis database number
        namespace: Redis key namespace

    Returns:
        Configured TokenBucketLimiter instance

    Raises:
        redis.ConnectionError: If cannot connect to Redis
    """
    config = RateLimitConfig(
        requests_per_period=requests_per_period,
        period_seconds=period_seconds,
        strategy=RateLimitStrategy.TOKEN_BUCKET,
        burst_size=burst_size,
    )

    try:
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True,
        )
        redis_client.ping()
    except redis.ConnectionError as e:
        raise redis.ConnectionError(f"Failed to connect to Redis: {e}")

    return TokenBucketLimiter(config=config, redis_client=redis_client, namespace=namespace)

