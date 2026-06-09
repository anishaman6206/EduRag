"""
GET /health — liveness + readiness check.

Probes each backend service and reports per-service status. The
overall status is 'ok' if every check passes, 'degraded' if any
non-critical check fails. (Currently all checks are critical.)

This is the endpoint to point your monitoring/load-balancer at.
"""

from __future__ import annotations
import asyncio
import logging

from fastapi import APIRouter
from pinecone import Pinecone

from config.settings import get_settings
from models.response_models import HealthCheck, HealthResponse
from services.openai_service import get_openai
from services.supabase_service import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


async def _check_openai() -> HealthCheck:
    try:
        client = get_openai()
        # Cheapest possible ping: a 1-token completion
        response = await client.embeddings.create(
            model=get_settings().openai_embedding_model,
            input="health",
        )
        if response.data and len(response.data[0].embedding) == 1536:
            return HealthCheck(status="ok")
        return HealthCheck(status="error", detail="Unexpected embedding response")
    except Exception as e:
        return HealthCheck(status="error", detail=str(e)[:200])


async def _check_pinecone() -> HealthCheck:
    try:
        s = get_settings()
        pc = Pinecone(api_key=s.pinecone_api_key)
        # list_indexes is a cheap API call that exercises auth + DNS
        pc.list_indexes()
        return HealthCheck(status="ok")
    except Exception as e:
        return HealthCheck(status="error", detail=str(e)[:200])


async def _check_supabase() -> HealthCheck:
    try:
        c = get_supabase()
        c.storage.list_buckets()
        return HealthCheck(status="ok")
    except Exception as e:
        return HealthCheck(status="error", detail=str(e)[:200])


async def _check_redis() -> HealthCheck:
    try:
        from services.redis_service import get_redis
        r = get_redis()
        await r.ping()
        return HealthCheck(status="ok")
    except Exception as e:
        # Redis is the only non-critical dependency — we have an
        # in-memory fallback. Mark as 'degraded' but still ok overall.
        return HealthCheck(status="degraded", detail=str(e)[:200])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Run all checks in parallel and aggregate."""
    openai_check, pinecone_check, supabase_check, redis_check = await asyncio.gather(
        _check_openai(),
        _check_pinecone(),
        _check_supabase(),
        _check_redis(),
        return_exceptions=False,
    )

    checks = {
        "openai": openai_check,
        "pinecone": pinecone_check,
        "supabase": supabase_check,
        "redis": redis_check,
    }

    # All checks must be 'ok' for the service to be 'ok'.
    # 'degraded' on redis is allowed; anything else flips overall to 'degraded'.
    overall = "ok"
    for name, ch in checks.items():
        if ch.status == "error":
            overall = "degraded"
            break
        if ch.status == "degraded" and overall == "ok":
            overall = "degraded"

    return HealthResponse(status=overall, checks=checks)
