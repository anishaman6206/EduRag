"""
Redis cache client.

Two patterns used:
  - Simple get/set with TTL for /ask answer caching (key includes a
    hash of the query string so similar questions are not falsely merged).
  - Optional in-memory fallback when Redis is unreachable so the API
    still serves in dev with a misconfigured REDIS_URL.
"""

from __future__ import annotations
import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from config.settings import get_settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
# Tiny in-memory fallback (per-process) used only if Redis is down.
_mem_fallback: dict[str, str] = {}


def get_redis() -> aioredis.Redis:
    """Lazy-init the async Redis client."""
    global _redis
    if _redis is None:
        s = get_settings()
        _redis = aioredis.from_url(
            s.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis client initialized (url=%s)", s.redis_url)
    return _redis


def make_cache_key(query: str, class_level: str, subject: str | None) -> str:
    """
    Deterministic cache key. Hashes the lowercased + trimmed query so
    'What is 2+2?' and 'what is 2+2 ?' collide.
    """
    payload = f"{class_level}|{subject or 'any'}|{query.strip().lower()}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"edurag:ask:{class_level}:{subject or 'any'}:{digest}"


async def cache_get(key: str) -> dict[str, Any] | None:
    """Return a cached dict, or None on miss / Redis failure."""
    try:
        raw = await get_redis().get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("Redis GET failed for %s: %s — using memory fallback", key, e)
        raw = _mem_fallback.get(key)
        if raw:
            return json.loads(raw)
    return None


async def cache_set(key: str, value: dict[str, Any], ttl_seconds: int = 3600) -> None:
    """Cache a dict under `key` with a TTL (seconds)."""
    payload = json.dumps(value, default=str)
    try:
        await get_redis().setex(key, ttl_seconds, payload)
    except Exception as e:
        logger.warning("Redis SETEX failed for %s: %s — using memory fallback", key, e)
        _mem_fallback[key] = payload


async def cache_delete(key: str) -> None:
    """Invalidate a key. Used when a chat message gets re-saved."""
    try:
        await get_redis().delete(key)
    except Exception as e:
        logger.warning("Redis DEL failed for %s: %s", key, e)
        _mem_fallback.pop(key, None)
