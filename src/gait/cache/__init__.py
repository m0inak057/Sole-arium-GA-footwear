"""Caching module (Redis)."""

MODULE_STATUS = "UNUSED"
# Not imported by any live request path: RedisSessionStore (gait.api.session_store)
# and the MinIO wiring in gait.api.main talk to Redis/MinIO directly instead of
# going through this Cache abstraction. Kept as scaffolding for a future generic
# response/profile cache. To activate: build a Cache via create_redis_cache(),
# expose it as a FastAPI dependency, and call .get()/.set() around the endpoints
# that would benefit (e.g. GET /profile, GET /comparison).

from gait.cache.base import Cache, CacheConfig
from gait.cache.dependencies import create_redis_cache
from gait.cache.redis_cache import RedisCache

__all__ = [
    "Cache",
    "CacheConfig",
    "RedisCache",
    "create_redis_cache",
]

