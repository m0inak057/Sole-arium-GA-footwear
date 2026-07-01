"""Unit tests for rate limiting."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import redis

from gait.rate_limit.base import (
    RateLimitConfig,
    RateLimitError,
    RateLimitStrategy,
)
from gait.rate_limit.dependencies import create_token_bucket_limiter
from gait.rate_limit.token_bucket import TokenBucketLimiter


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_create_config_defaults(self):
        """Test creating config with defaults."""
        config = RateLimitConfig(
            requests_per_period=100,
            period_seconds=60,
        )
        assert config.requests_per_period == 100
        assert config.period_seconds == 60
        assert config.strategy == RateLimitStrategy.TOKEN_BUCKET
        assert config.burst_size == 10

    def test_create_config_custom(self):
        """Test creating config with custom values."""
        config = RateLimitConfig(
            requests_per_period=50,
            period_seconds=30,
            burst_size=20,
        )
        assert config.requests_per_period == 50
        assert config.period_seconds == 30
        assert config.burst_size == 20


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_error(self):
        """Test RateLimitError creation."""
        error = RateLimitError("Rate limit exceeded", retry_after_seconds=60)
        assert error.message == "Rate limit exceeded"
        assert error.retry_after_seconds == 60

    def test_rate_limit_error_inheritance(self):
        """Test that RateLimitError is an Exception."""
        error = RateLimitError("Test", 60)
        assert isinstance(error, Exception)


class TestTokenBucketLimiterWithMock:
    """Tests for TokenBucketLimiter using mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create mocked Redis client."""
        with patch("redis.Redis") as mock:
            yield mock.return_value

    @pytest.fixture
    def limiter_config(self):
        """Create rate limit config."""
        return RateLimitConfig(
            requests_per_period=10,
            period_seconds=60,
            burst_size=5,
        )

    @pytest.fixture
    def limiter(self, limiter_config, mock_redis):
        """Create TokenBucketLimiter with mocked Redis."""
        return TokenBucketLimiter(limiter_config, mock_redis)

    def test_limiter_allows_request(self, limiter, mock_redis):
        """Test that request is allowed when within limit."""
        current_time = time.time()
        # First call: get current tokens (returns full burst), second call: get refill time (returns old time)
        mock_redis.get.side_effect = [str(limiter.config.burst_size), str(current_time - 10)]
        result = limiter.is_allowed("user123")
        assert result is True
        mock_redis.set.assert_called()

    def test_limiter_rate_limit_exceeded(self, limiter, mock_redis):
        """Test that rate limit is enforced."""
        # Bucket is empty (0 tokens)
        mock_redis.get.side_effect = [0.0, 0.0]
        with pytest.raises(RateLimitError):
            limiter.is_allowed("user123")

    def test_limiter_get_remaining_zero(self, limiter, mock_redis):
        """Test getting remaining requests when exhausted."""
        mock_redis.get.side_effect = [0.0, 0.0]
        remaining = limiter.get_remaining("user123")
        assert remaining == 0

    def test_limiter_get_remaining_positive(self, limiter, mock_redis):
        """Test getting remaining requests when available."""
        current_time = time.time()
        mock_redis.get.side_effect = [5.0, current_time]  # 5 tokens available
        remaining = limiter.get_remaining("user123")
        assert remaining >= 0

    def test_limiter_reset(self, limiter, mock_redis):
        """Test resetting rate limit."""
        result = limiter.reset("user123")
        assert result is True
        mock_redis.delete.assert_called_once()

    def test_limiter_reset_failure(self, limiter, mock_redis):
        """Test reset failure handling."""
        mock_redis.delete.side_effect = redis.RedisError("Error")
        result = limiter.reset("user123")
        assert result is False

    def test_limiter_get_reset_time(self, limiter, mock_redis):
        """Test getting reset time."""
        mock_redis.ttl.return_value = 30
        reset_time = limiter.get_reset_time("user123")
        assert reset_time > time.time()

    def test_limiter_get_reset_time_no_key(self, limiter, mock_redis):
        """Test getting reset time when key doesn't exist."""
        mock_redis.ttl.return_value = -2  # Key not found
        reset_time = limiter.get_reset_time("user123")
        assert reset_time > time.time()

    def test_limiter_redis_error_on_check(self, limiter, mock_redis):
        """Test handling Redis error during check."""
        mock_redis.get.side_effect = redis.RedisError("Connection error")
        # Should fail open (allow request)
        result = limiter.is_allowed("user123")
        assert result is True

    def test_limiter_make_key(self, limiter):
        """Test key creation."""
        tokens_key, refill_key = limiter._make_key("user123")
        assert tokens_key == "ratelimit:tokens:user123"
        assert refill_key == "ratelimit:refill:user123"

    def test_limiter_custom_namespace(self, limiter_config, mock_redis):
        """Test custom namespace."""
        limiter = TokenBucketLimiter(
            limiter_config,
            mock_redis,
            namespace="custom",
        )
        tokens_key, refill_key = limiter._make_key("user123")
        assert tokens_key.startswith("custom:")

    def test_limiter_burst_size_capping(self, limiter, mock_redis):
        """Test that tokens are capped at burst size."""
        # Simulate large elapsed time with high refill rate
        mock_redis.get.side_effect = [
            1000.0,  # Current tokens >> burst_size
            time.time() - 1000,  # Old refill time
        ]
        remaining = limiter.get_remaining("user123")
        # Should be capped at burst_size (5)
        assert remaining <= limiter.config.burst_size

    def test_limiter_close(self, limiter):
        """Test closing limiter."""
        limiter.close()  # Should not raise


class TestRateLimitDependencies:
    """Tests for rate limit dependencies."""

    def test_create_token_bucket_limiter_defaults(self):
        """Test creating token bucket limiter with defaults."""
        with patch("gait.rate_limit.dependencies.redis.Redis") as mock_redis:
            mock_instance = MagicMock()
            mock_redis.return_value = mock_instance
            mock_instance.ping.return_value = True

            limiter = create_token_bucket_limiter()
            assert isinstance(limiter, TokenBucketLimiter)

    def test_create_token_bucket_limiter_custom(self):
        """Test creating token bucket limiter with custom values."""
        with patch("gait.rate_limit.dependencies.redis.Redis") as mock_redis:
            mock_instance = MagicMock()
            mock_redis.return_value = mock_instance
            mock_instance.ping.return_value = True

            limiter = create_token_bucket_limiter(
                requests_per_period=50,
                period_seconds=30,
                burst_size=15,
            )
            assert limiter.config.requests_per_period == 50
            assert limiter.config.period_seconds == 30
            assert limiter.config.burst_size == 15

    def test_create_token_bucket_limiter_connection_error(self):
        """Test handling Redis connection error."""
        with patch("gait.rate_limit.dependencies.redis.Redis") as mock_redis:
            mock_redis.side_effect = redis.ConnectionError("Cannot connect")
            with pytest.raises(redis.ConnectionError):
                create_token_bucket_limiter()


