"""
Per-user rate limiter for /ask.

Uses Redis sliding-window counters. Falls back to "allow" when Redis
is unreachable so a Redis outage doesn't break the API.

Design:
  - Limit is requests per minute (configurable via env).
  - Key is `edurag:rl:<bucket>:<identifier>` (bucket = "ask",
    identifier = user_id or "ip:<addr>" for anonymous).
  - On every call we INCR the counter and set EX=60 on first hit.
  - Reject (with HTTP 429) when count > limit.

This is intentionally simple — it caps a single user's burst, not
sustained throughput. A real abuse pattern (someone spinning up
many anon IDs) needs Cloudflare Turnstile on the frontend first;
this layer is the second line of defense.

Why sliding-window-via-INCR (not a real sliding window):
  - One Redis round trip per request.
  - Slight overcount at minute boundaries is fine for our purpose
    (we're capping abuse, not metering for billing).
"""

from __future__ import annotations
import logging

from fastapi import HTTPException, Request

from services import redis_service

logger = logging.getLogger(__name__)


# Default: 30 asks per minute per user_id. Generous for legitimate
# re-asking during a study session; well below what an abuser would
# need to drain an OpenAI budget in a short window.
DEFAULT_LIMIT_PER_MINUTE = 30


def _get_limit() -> int:
    """Read ASK_RATE_LIMIT_PER_MINUTE from the env, fall back to default."""
    import os
    raw = os.environ.get("ASK_RATE_LIMIT_PER_MINUTE", str(DEFAULT_LIMIT_PER_MINUTE))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_LIMIT_PER_MINUTE


async def _client_ip(request: Request) -> str:
    """Best-effort client IP. Honor X-Forwarded-For if behind a proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # First entry is the original client
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "unknown")


async def enforce_rate_limit(request: Request, user_id: str) -> None:
    """
    Call at the top of /ask. Raises HTTP 429 if the user is over the
    per-minute limit. No-op when Redis is unreachable (fail-open is
    safer than fail-closed for an educational tool).

    Identifying key is `user_id` when it's a real user, otherwise the
    client IP. The `anonymous` fallback user_id is split by IP so a
    classroom full of unauthenticated students doesn't all share one
    bucket.
    """
    # Disabled when the env var is set to 0 — useful for load testing.
    limit = _get_limit()
    if limit <= 0:
        return

    # Skip the rate limit silently if Redis has already been marked
    # down for this process (avoids hammering a dead Redis on every
    # request — same fast-path pattern as cache_get).
    if redis_service.redis_is_known_down():
        return

    identifier = user_id if user_id and user_id != "anonymous" else f"ip:{await _client_ip(request)}"
    key = f"edurag:rl:ask:{identifier}"

    try:
        client = redis_service.get_redis()
        # INCR is atomic; first hit creates the key, subsequent hits
        # increment. EXPIRE sets the TTL only on the first hit (NX
        # would be cleaner but requires a Lua script; for our use,
        # re-setting EX every time is harmless — the TTL stays 60s).
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 60)
        if count > limit:
            logger.warning("Rate limit hit for %s (%d/%d)", identifier, count, limit)
            raise HTTPException(
                status_code=429,
                detail=f"Too many questions. Please wait a minute. (Limit: {limit}/min)",
                headers={"Retry-After": "60"},
            )
    except HTTPException:
        raise
    except Exception as e:
        # Fail-open: if Redis hiccups, let the request through.
        logger.warning("Rate limit check failed (allowing request): %s", e)
        redis_service.mark_redis_down()