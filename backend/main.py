"""
EduRag FastAPI entry point.

Run locally:
    cd backend
    uvicorn main:app --reload --port 8000

Run in Docker:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import query, history, health, chapters


# ─────────────────────────────────────────────────────────────────────────
# Logging — clear format, INFO by default, DEBUG if LOG_LEVEL=debug
# ─────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="EduRag API",
    description="RAG-based doubt solver for Class 7-9 PCM, grounded in NCERT chapters.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─────────────────────────────────────────────────────────────────────────
# CORS
# Origins are env-driven. Defaults are safe for local dev (localhost
# frontend on a different port). For production, set
# CORS_ALLOWED_ORIGINS to the exact frontend domain(s) — never leave
# it as "*" because we use allow_credentials=True (cookies / auth
# headers), and browsers reject the combination of wildcard +
# credentials.
#
# Example prod value:
#   CORS_ALLOWED_ORIGINS=https://edurag.vercel.app,https://edurag.com
# ─────────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",") if o.strip()
]

# Allow all methods/headers only when running locally. In production,
# we narrow to exactly what /ask, /history, /chapters, /health need.
IS_PROD = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip() != ""

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["Content-Type"],
)


# ─────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────
app.include_router(query.router, tags=["ask"])
app.include_router(history.router, tags=["history"])
app.include_router(health.router, tags=["health"])
app.include_router(chapters.router, tags=["chapters"])


# ─────────────────────────────────────────────────────────────────────────
# Startup / shutdown hooks
# ─────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def _on_startup() -> None:
    logger.info("EduRag API starting up")
    # Eager-init the OpenAI + Pinecone + Supabase clients so any
    # auth errors surface at boot, not on the first /ask.
    try:
        from services.openai_service import get_openai
        from services.pinecone_service import get_index
        from services.supabase_service import get_supabase
        from config.settings import get_settings

        s = get_settings()
        get_openai()
        get_index()
        get_supabase()
        logger.info(
            "Services initialized (env=%s, models=%s, has_cohere=%s)",
            s.environment, s.models, s.has_cohere,
        )
    except Exception as e:
        # We don't want to crash on startup if, say, Supabase is
        # briefly unreachable. Log loudly so it's visible.
        logger.error("Service init failed (will retry on first request): %s", e)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root — returns basic API info. Useful for sanity-checking deployment."""
    return {
        "name": "EduRag API",
        "version": "0.1.0",
        "endpoints": ["/ask", "/history", "/health", "/docs"],
    }
