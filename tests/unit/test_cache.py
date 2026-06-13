"""Unit tests for caching layer."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
import redis

from src.gait.cache.base import Cache, CacheConfig
from src.gait.cache.redis_cache import RedisCache
from src.gait.cache.dependencies import create_redis_cache


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_create_config_defaults(self):
        """Test creating config with defaults."""
        config = CacheConfig()
        assert config.default_ttl_seconds == 3600
        assert config.max_ttl_seconds == 86400
        assert config.namespace == "gait"

    def test_create_config_custom(self):
        """Test creating config with custom values."""
        config = CacheConfig(
            default_ttl_seconds=1800,
            max_ttl_seconds=3600,
            namespace="test",
        )
        assert config.default_ttl_seconds == 1800
        assert config.max_ttl_seconds == 3600
        assert config.namespace == "test"


class TestRedisCacheWithMock:
    """Tests for RedisCache using mocked Redis."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create mocked Redis client."""
        with patch("redis.Redis") as mock_redis:
            mock_instance = MagicMock()
            mock_redis.return_value = mock_instance
            # Mock successful ping
            mock_instance.ping.return_value = True
            yield mock_instance

    @pytest.fixture
    def cache_config(self):
        """Create cache config."""
        return CacheConfig(namespace="test")

    @pytest.fixture
    def redis_cache(self, cache_config, mock_redis_client):
        """Create RedisCache with mocked client."""
        with patch("redis.Redis") as mock_redis:
            mock_redis.return_value = mock_redis_client
            cache = RedisCache(cache_config)
            cache.redis_client = mock_redis_client
            return cache

    def test_cache_set_string(self, redis_cache, mock_redis_client):
        """Test setting string value."""
        result = redis_cache.set("key1", "value1", ttl_seconds=3600)
        assert result is True
        mock_redis_client.setex.assert_called_once()

    def test_cache_get_string(self, redis_cache, mock_redis_client):
        """Test getting string value."""
        mock_redis_client.get.return_value = "value1"
        result = redis_cache.get("key1")
        assert result == "value1"

    def test_cache_get_json(self, redis_cache, mock_redis_client):
        """Test getting JSON value."""
        expected = {"key": "value"}
        mock_redis_client.get.return_value = json.dumps(expected)
        result = redis_cache.get("key1")
        assert result == expected

    def test_cache_get_miss(self, redis_cache, mock_redis_client):
        """Test cache miss."""
        mock_redis_client.get.return_value = None
        result = redis_cache.get("nonexistent")
        assert result is None

    def test_cache_delete(self, redis_cache, mock_redis_client):
        """Test deleting key."""
        mock_redis_client.delete.return_value = 1
        result = redis_cache.delete("key1")
        assert result is True

    def test_cache_delete_not_found(self, redis_cache, mock_redis_client):
        """Test deleting non-existent key."""
        mock_redis_client.delete.return_value = 0
        result = redis_cache.delete("nonexistent")
        assert result is False

    def test_cache_exists(self, redis_cache, mock_redis_client):
        """Test checking key existence."""
        mock_redis_client.exists.return_value = 1
        result = redis_cache.exists("key1")
        assert result is True

    def test_cache_exists_not_found(self, redis_cache, mock_redis_client):
        """Test existence check for non-existent key."""
        mock_redis_client.exists.return_value = 0
        result = redis_cache.exists("nonexistent")
        assert result is False

    def test_cache_clear(self, redis_cache, mock_redis_client):
        """Test clearing cache."""
        mock_redis_client.keys.return_value = ["test:key1", "test:key2"]
        result = redis_cache.clear()
        assert result is True
        mock_redis_client.delete.assert_called_once()

    def test_cache_clear_empty(self, redis_cache, mock_redis_client):
        """Test clearing empty cache."""
        mock_redis_client.keys.return_value = []
        result = redis_cache.clear()
        assert result is True

    def test_cache_get_ttl(self, redis_cache, mock_redis_client):
        """Test getting TTL."""
        mock_redis_client.ttl.return_value = 3600
        result = redis_cache.get_ttl("key1")
        assert result == 3600

    def test_cache_get_ttl_no_expiry(self, redis_cache, mock_redis_client):
        """Test getting TTL for key with no expiry."""
        mock_redis_client.ttl.return_value = -1
        result = redis_cache.get_ttl("key1")
        assert result == -1

    def test_cache_get_ttl_not_found(self, redis_cache, mock_redis_client):
        """Test getting TTL for non-existent key."""
        mock_redis_client.ttl.return_value = -2
        result = redis_cache.get_ttl("nonexistent")
        assert result == -2

    def test_cache_set_invalid_ttl(self, redis_cache, mock_redis_client):
        """Test setting with invalid TTL (negative)."""
        result = redis_cache.set("key1", "value", ttl_seconds=-1)
        assert result is False

    def test_cache_set_ttl_capped(self, redis_cache, mock_redis_client):
        """Test TTL capped at max."""
        redis_cache.set("key1", "value", ttl_seconds=999999)
        # Should call with max_ttl_seconds
        called_ttl = mock_redis_client.setex.call_args[0][1]
        assert called_ttl == redis_cache.config.max_ttl_seconds

    def test_cache_set_uses_default_ttl(self, redis_cache, mock_redis_client):
        """Test using default TTL."""
        redis_cache.set("key1", "value")
        # Should use default TTL
        called_ttl = mock_redis_client.setex.call_args[0][1]
        assert called_ttl == redis_cache.config.default_ttl_seconds

    def test_cache_context_manager(self, redis_cache, mock_redis_client):
        """Test context manager support."""
        with redis_cache:
            pass
        mock_redis_client.close.assert_called_once()

    def test_cache_redis_error_on_get(self, redis_cache, mock_redis_client):
        """Test handling Redis error on get."""
        mock_redis_client.get.side_effect = redis.RedisError("Connection error")
        result = redis_cache.get("key1")
        assert result is None

    def test_cache_redis_error_on_set(self, redis_cache, mock_redis_client):
        """Test handling Redis error on set."""
        mock_redis_client.setex.side_effect = redis.RedisError("Connection error")
        result = redis_cache.set("key1", "value")
        assert result is False

    def test_make_key_namespaced(self, redis_cache):
        """Test that keys are properly namespaced."""
        key = redis_cache._make_key("mykey")
        assert key == "test:mykey"


class TestCacheDependencies:
    """Tests for cache dependencies."""

    def test_create_redis_cache_defaults(self):
        """Test creating Redis cache with defaults."""
        with patch("src.gait.cache.dependencies.RedisCache") as mock_cache:
            mock_cache.return_value = MagicMock()
            cache = create_redis_cache()
            mock_cache.assert_called_once()
            args, kwargs = mock_cache.call_args
            assert kwargs["host"] == "localhost"
            assert kwargs["port"] == 6379
            assert kwargs["db"] == 0

    def test_create_redis_cache_custom(self):
        """Test creating Redis cache with custom values."""
        with patch("src.gait.cache.dependencies.RedisCache") as mock_cache:
            mock_cache.return_value = MagicMock()
            cache = create_redis_cache(
                host="redis.example.com",
                port=6380,
                db=1,
            )
            args, kwargs = mock_cache.call_args
            assert kwargs["host"] == "redis.example.com"
            assert kwargs["port"] == 6380
            assert kwargs["db"] == 1
