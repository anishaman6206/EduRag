# EduRag

> Production-grade RAG-based doubt-solving web app for **Class 7, 8, and 9 PCM**
> (Physics, Chemistry, Mathematics) students. Answers are grounded in
> NCERT textbook chapters, with diagrams and LaTeX rendered inline.

---

## Table of contents

1. [What is EduRag?](#1-what-is-edurag)
2. [Tech stack](#2-tech-stack)
3. [Architecture](#3-architecture)
4. [Repository layout](#4-repository-layout)
5. [Build status — what's done, what's next](#5-build-status)
6. [Local setup](#6-local-setup)
7. [Environment variables reference](#7-environment-variables-reference)
8. [Ingesting a chapter](#8-ingesting-a-chapter)
9. [API surface](#9-api-surface)
10. [The RAG pipeline in detail](#10-the-rag-pipeline-in-detail)
11. [Vision / diagram processing (planned)](#11-vision--diagram-processing-planned)
12. [Dev mode vs Production mode](#12-dev-mode-vs-production-mode)
13. [Known limitations](#13-known-limitations)
14. [Roadmap](#14-roadmap)

---

## 1. What is EduRag?

EduRag is a web app where a Class 7-9 PCM student can ask a question
("What is Newton's second law?") and receive:

- A **step-by-step, LaTeX-rendered answer** appropriate for their grade level
- **Inline diagrams** pulled from the relevant NCERT textbook page
- **Source citations** showing the exact chunk(s) the answer was grounded in
- An optional **subject + class filter** so the student can scope retrieval

The system uses **Retrieval-Augmented Generation (RAG)** over NCERT
textbook chapters, with one Pinecone namespace per chapter. There is
**no fine-tuning** — only chunking, embedding, and in-context generation.

### Why RAG over NCERT specifically?

- NCERT is the canonical syllabus for Indian schools.
- Students often ask "in the textbook" questions that require precise page-level grounding, which LLMs hallucinate without context.
- A new textbook edition (or a state-board book) can be added by simply re-ingesting — no model retraining.

---

## 2. Tech stack

| Concern | Choice | Why |
|---|---|---|
| Backend framework | **FastAPI** (Python 3.11+) | Async-native, great streaming support (SSE) |
| Frontend | **Next.js 14** + TypeScript + Tailwind | SSR + streaming-friendly |
| Vector DB | **Pinecone** | Serverless, namespace-per-chapter isolation |
| Text + embedding LLM | **OpenAI** (`gpt-4o-mini` + `text-embedding-3-small`) | Single API, one bill, fast |
| Cache | **Redis** | /ask response cache, idempotency |
| Database | **Supabase** (Postgres) | Chat history, parent-chunk storage, diagram images |
| Reranker | **Cohere** `rerank-english-v3.0` | Optional — skipped if no key |
| Containerization | **Docker Compose** | One-command local dev |
| PDF parsing | **PyMuPDF** (fitz) | Fast, handles embedded images |
| BM25 sparse search | **rank_bm25** | Hybrid retrieval, no extra service |

### OpenAI was chosen over Anthropic for this build

- One provider = one API key, one billing relationship, one SDK to maintain.
- `gpt-4o-mini` is fast and cheap enough for development.
- Streaming, JSON mode, and embeddings are all in the same SDK.

---

## 3. Architecture

```
                         ┌──────────────────────────────────────┐
                         │  Student browser (Next.js client)    │
                         │  - Chat UI, LaTeX (KaTeX), diagrams  │
                         └────────────────┬─────────────────────┘
                                          │  POST /ask  (SSE stream)
                                          ▼
                ┌─────────────────────────────────────────────────┐
                │  FastAPI backend (uvicorn, port 8000)           │
                │                                                 │
                │   ┌─────────┐   ┌──────────┐   ┌────────────┐  │
                │   │ classify│ → │ retrieve │ → │  rerank    │  │
                │   │ (LLM)   │   │  hybrid  │   │ (Cohere*)  │  │
                │   └─────────┘   └────┬─────┘   └─────┬──────┘  │
                │                      │                │         │
                │                      ▼                ▼         │
                │                ┌──────────────────────────┐    │
                │                │ generate (gpt-4o-mini)   │    │
                │                │ streaming SSE            │    │
                │                └──────────┬───────────────┘    │
                └────────────────────────┬──┴────────────────────┘
                                         │
        ┌────────────────────────────────┼─────────────────────────────────┐
        │                                │                                 │
        ▼                                ▼                                 ▼
  ┌──────────┐                   ┌──────────────┐                  ┌──────────────┐
  │ Redis    │                   │  Pinecone    │                  │  Supabase    │
  │ cache    │                   │  namespaces  │                  │  - chat_msgs │
  │ (1h TTL) │                   │  (per chap.) │                  │  - parent_   │
  │          │                   │              │                  │    chunks    │
  │          │                   │  dense:embed │                  │  - storage   │
  │          │                   │  sparse:BM25 │                  │    (diagrams)│
  └──────────┘                   └──────────────┘                  └──────────────┘

  *  Cohere rerank is OPTIONAL — skipped silently if COHERE_API_KEY is empty.

  Ingestion (separate path, run via CLI):
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐
  │ PDF parse│ →  │  chunk   │ →  │ embed    │ →  │ upsert   │ →  │  diagram     │
  │ (PyMuPDF)│    │ semantic │    │  OpenAI  │    │ Pinecone │    │  vision (LLM)│
  │          │    │ parent+  │    │  1536-d  │    │ + parent │    │  + Supabase  │
  │          │    │ child    │    │          │    │   to DB  │    │    storage   │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────────┘
```

---

## 4. Repository layout

```
edurag/
├── backend/
│   ├── main.py                      # FastAPI app entry
│   ├── requirements.txt
│   ├── .env.example                 # Copy to .env, fill in keys
│   ├── Dockerfile
│   ├── api/
│   │   └── routes/
│   │       ├── query.py             # POST /ask (SSE)
│   │       ├── history.py           # GET /history
│   │       └── health.py            # GET /health
│   ├── rag/
│   │   ├── classifier.py            # LLM-based query → (subject, class, chapter)
│   │   ├── retriever.py             # Pinecone dense + BM25 sparse + RRF fusion
│   │   ├── reranker.py              # Cohere rerank (optional)
│   │   └── generator.py             # Streaming answer + diagrams + sources SSE
│   ├── ingestion/
│   │   ├── pdf_parser.py            # PyMuPDF — text + embedded images + captions
│   │   ├── chunker.py               # Semantic chunking, parent/child
│   │   ├── diagram_processor.py     # Vision LLM — diagram → description
│   │   ├── embedder.py              # OpenAI 1536-d embeddings
│   │   └── pipeline.py              # Full ingest orchestrator
│   ├── services/
│   │   ├── openai_service.py        # gpt-4o-mini + text-embedding-3-small
│   │   ├── pinecone_service.py      # index, namespace, idempotent upsert
│   │   ├── supabase_service.py      # chat history, parent chunks, storage
│   │   ├── redis_service.py         # cache with in-memory fallback
│   │   └── cohere_service.py        # optional rerank
│   ├── models/
│   │   ├── request_models.py        # Pydantic request schemas
│   │   └── response_models.py       # Pydantic response schemas
│   └── config/
│       ├── settings.py              # Pydantic BaseSettings + MODELS dict
│       └── constants.py             # NAMESPACE_MAP (55 chapters) + 3 prompts
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.ts
│   ├── .env.local.example
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx                       # Landing / redirect
│       │   └── chat/page.tsx                  # Main chat interface
│       ├── components/
│       │   ├── Chat/
│       │   │   ├── ChatWindow.tsx
│       │   │   ├── MessageBubble.tsx
│       │   │   ├── QueryInput.tsx
│       │   │   └── StreamingDots.tsx
│       │   ├── Diagram/DiagramCard.tsx
│       │   ├── Filters/SubjectClassFilter.tsx
│       │   └── UI/
│       │       ├── LatexRenderer.tsx          # KaTeX wrapper
│       │       └── SourceCard.tsx
│       ├── hooks/
│       │   ├── useChat.ts
│       │   └── useStream.ts                   # SSE reader
│       ├── lib/
│       │   ├── api.ts
│       │   └── types.ts
│       └── store/
│           └── chatStore.ts                   # Zustand
│
├── scripts/
│   ├── ingest_chapter.py             # CLI: ingest one chapter
│   └── ingest_all.py                 # CLI: ingest every chapter
│
├── docker-compose.yml
├── .gitignore
└── README.md                         # this file
```

---

## 5. Build status

We build **step by step**, commit after each step, and only then move on.

| # | Component | Status | Notes |
|---|---|---|---|
| 1 | `requirements.txt` + `package.json` | done | pinned versions |
| 2 | `backend/config/constants.py` | done | 22 chapters aligned with the actual NCERT PDFs in `pdfs/Data/`, 3 prompts |
| 3 | `backend/config/settings.py` | done | OpenAI gpt-4o-mini + DEV_MODE |
| 4 | `backend/services/` (5 files) | done | openai, pinecone, supabase, redis, cohere |
| 5 | `backend/rag/` | done | classifier, retriever (hybrid dense + BM25), reranker, generator with status SSE events |
| 6 | `backend/api/routes/` | done | query (SSE), history, health |
| 7 | `backend/ingestion/` | done | parser, chunker, diagram_processor, embedder, pipeline with incremental upsert |
| 8 | `frontend/` | done | hooks, components, store, pages, Supabase Auth (email magic link) |
| 9 | `docker-compose.yml`, `scripts/`, full README updates | done | all three services wired up |

What works **today**: full end-to-end RAG pipeline. `POST /ask` streams
SSE events (status → token → diagrams → sources → done) to the
Next.js frontend, which renders Markdown + LaTeX + diagram images
in real time. Supabase stores chat history and parent chunks;
Pinecone holds the per-chapter vector namespaces. Incremental
ingest via `scripts/ingest_chapter.py --upload-diagrams` re-uploads
diagram images and writes the public URLs back into Pinecone metadata.

---

## 6. Local setup

### Option A — One-command Docker (recommended)

```bash
git clone <repo>
cd edurag
cp backend/.env.example backend/.env       # then fill in your keys
cp frontend/.env.local.example frontend/.env.local   # then fill in Supabase
docker-compose up --build
```

That's it. Open:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API docs (Swagger)**: http://localhost:8000/docs
- **Redis**: localhost:6379

Hot-reload is enabled for the backend (`uvicorn --reload` via the
volume mount). The frontend uses the production build inside Docker;
for frontend hot-reload, run it directly on the host (Option B).

### Option B — Run services on the host

For frontend hot-reload (faster iteration on UI code), run the
backend + redis in Docker but the frontend on your host:

```bash
# Terminal 1: backend + redis
docker-compose up backend redis

# Terminal 2: frontend (with hot-reload)
cd frontend
cp .env.local.example .env.local     # then fill in
BACKEND_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

### Option C — Everything on the host (no Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                                # then fill in
# Start redis somehow (Docker, native, brew, etc.) — backend needs REDIS_URL
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
cp .env.local.example .env.local                    # then fill in
BACKEND_URL=http://localhost:8000 npm run dev
```

### Prerequisites
- An **OpenAI** account with credits (text + embeddings)
- A **Pinecone** account (free tier is fine)
- A **Supabase** project (free tier is fine)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your keys
```

Verify everything is wired up:

```bash
python -c "
import asyncio
from config.settings import get_settings
from services.openai_service import get_embedding
from services.pinecone_service import get_index
from services.supabase_service import get_supabase

async def go():
    s = get_settings()
    print('env:', s.environment)
    v = await get_embedding('hello')
    print('embedding dim:', len(v))
    idx = get_index()
    print('pinecone index:', idx.name, 'vectors:', idx.describe_index_stats().total_vector_count)
    print('supabase buckets:', [b.name for b in get_supabase().storage.list_buckets()])

asyncio.run(go())
"
```

You should see `embedding dim: 1536`, a Pinecone vector count, and
your Supabase buckets (probably `[]` until you create the `diagrams` one).

### Run the API (once step 6 is built)

```bash
uvicorn main:app --reload --port 8000
```

### Run the frontend (once step 8 is built)

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
# → http://localhost:3000
```

### Run the full stack via Docker (once step 9 is built)

```bash
docker-compose up
# Backend:  http://localhost:8000
# Frontend: http://localhost:3000
# Redis:    localhost:6379
```

---

## 7. Environment variables reference

All variables live in `backend/.env` (gitignored). Copy `.env.example`
to start.

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | **yes** | — | Text + embeddings |
| `OPENAI_TEXT_MODEL` | no | `gpt-4o-mini` | All LLM roles |
| `OPENAI_EMBEDDING_MODEL` | no | `text-embedding-3-small` | 1536-d vectors |
| `PINECONE_API_KEY` | **yes** | — | Vector DB |
| `PINECONE_INDEX_NAME` | no | `edurag` | Created on first use |
| `SUPABASE_URL` | **yes** | — | Postgres + Storage |
| `SUPABASE_SERVICE_KEY` | **yes** | — | Server-side only — never expose to the browser |
| `REDIS_URL` | no | `redis://localhost:6379` | Use `redis://redis:6379` inside docker-compose |
| `COHERE_API_KEY` | no | empty | Rerank skipped if empty |
| `DEV_MODE` | no | `true` | Currently a no-op (same model either way) |

**Do NOT commit `.env`.** It's already in `.gitignore`.

> ⚠️ **Security note**: when you finish a build session, rotate your
> API keys. Anything pasted into the conversation is visible in the
> transcript.

---

## 8. Ingesting a chapter

The full ingestion pipeline parses NCERT PDFs, chunks them
semantically, embeds the chunks, and upserts to Pinecone.

### Single chapter

```bash
# Parse + chunk + embed + upsert (no diagram upload)
PYTHONPATH=backend python scripts/ingest_chapter.py \
    --chapter-key physics_8_ch4 \
    --pdf "pdfs/Data/8th Science/hecu104.pdf"

# Same, but also upload diagram images to Supabase Storage
PYTHONPATH=backend python scripts/ingest_chapter.py \
    --chapter-key physics_8_ch4 \
    --pdf "pdfs/Data/8th Science/hecu104.pdf" \
    --upload-diagrams

# Dry-run (parse + chunk only, no embeddings or upserts)
PYTHONPATH=backend python scripts/ingest_chapter.py \
    --chapter-key physics_8_ch4 \
    --pdf "pdfs/Data/8th Science/hecu104.pdf" \
    --dry-run
```

The CLI:

1. Validates the chapter key exists in `NAMESPACE_MAP`.
2. Parses the PDF (text + embedded images).
3. Chunks semantically into parent (~1200 tok) and child (~300 tok).
4. Embeds children and upserts to the chapter's Pinecone namespace.
5. Stores parents in Supabase (Postgres).
6. With `--upload-diagrams`: uploads each diagram image to
   Supabase Storage and writes the public URL into the chunk's
   Pinecone metadata so the frontend can render `<img>` tags.
7. Prints a summary: parents, children, diagrams, vectors upserted.

### All chapters at once

```bash
# Plan only (no actual ingest)
PYTHONPATH=backend python scripts/ingest_all.py --dry-run

# Ingest every chapter in NAMESPACE_MAP
PYTHONPATH=backend python scripts/ingest_all.py

# Ingest a subset
PYTHONPATH=backend python scripts/ingest_all.py --class-filter 8
PYTHONPATH=backend python scripts/ingest_all.py --subject-filter physics
PYTHONPATH=backend python scripts/ingest_all.py --upload-diagrams
```

Expected time for the full 22-chapter ingest:

- Without `--upload-diagrams`: **~10-15 minutes**
- With `--upload-diagrams`: **~15-25 minutes**

Cost: ~$0.03 in OpenAI embeddings (no LLM is called at ingest time).

### Idempotency

**Re-ingesting a chapter is safe.** Each chunk has a deterministic ID
(`{chapter_key}_{idx}_{parent_content_hash[:8]}`) and a `version_hash`
of its content. On re-run:

- Chunks with the same content are **skipped** (no work, no API calls).
- Chunks with new/changed content are **upserted** (new embeddings).
- Chunks that no longer exist (e.g. after a chunker change) are **deleted**.
- Parents are upserted in Postgres via `on_conflict=id`.
- Diagrams re-upload with the new `version_hash` if you pass
  `--upload-diagrams` (the public URL is treated as part of the
  diagram's content for hash purposes).

---

## 9. API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ask` | Send a question, get a streaming SSE answer |
| `GET`  | `/history?user_id=…` | Last N messages for a user |
| `GET`  | `/health` | Liveness + readiness check (verifies OpenAI, Pinecone, Supabase, Redis) |

### `POST /ask`

**Request body**:
```json
{
  "query": "What is Newton's second law?",
  "class_level": "9",
  "subject": "physics",        // optional; omit to let classifier decide
  "user_id": "anon-abc123"     // optional; defaults to anonymous
}
```

**Response**: `text/event-stream` with these event types:

```
data: {"type": "token",     "content": "Newton's second law states..."}
data: {"type": "token",     "content": " that the net force..."}
...
data: {"type": "diagrams",  "data": [{"url": "https://...", "caption": "Fig 9.3"}]}
data: {"type": "sources",   "data": [{"chapter_key": "physics_9_ch10", "preview": "F = ma..."}]}
data: {"type": "done"}
```

### `GET /health`

```json
{
  "status": "ok",
  "checks": {
    "openai": "ok",
    "pinecone": "ok",
    "supabase": "ok",
    "redis": "ok"            // or "skipped" if REDIS_URL is empty
  }
}
```

---

## 10. The RAG pipeline in detail

### Step A — Classify

`rag/classifier.py` calls `gpt-4o-mini` in **JSON mode** with
`CLASSIFIER_PROMPT` (built dynamically from `NAMESPACE_MAP.keys()`).
Output:

```json
{
  "subject": "physics",
  "class_level": "9",
  "chapter_key": "physics_9_ch10",
  "confidence": 0.92
}
```

If `chapter_key` is null, the retriever falls back to searching
**all chapters of that subject + class**.

### Step B — Retrieve (hybrid)

`rag/retriever.py` runs two searches in parallel and fuses them:

1. **Dense** — Pinecone vector search on the resolved namespace, top-K=20.
2. **Sparse** — BM25 over the same set of chunks (we cache the corpus in-memory per namespace, rebuilt on first use).

Results are merged with **Reciprocal Rank Fusion**:
```
rrf_score(d) = α / (k + dense_rank(d)) + (1-α) / (k + sparse_rank(d))
```
where `α = 0.7` (dense-dominant — embeddings usually beat keyword for physics/math).

### Step C — Rerank (optional)

`rag/reranker.py` calls Cohere `rerank-english-v3-0` if `COHERE_API_KEY`
is set, taking the top 20 from RRF and returning the top 8.

### Parent / child chunk shape

This is the actual on-disk structure produced by `ingestion/chunker.py`
and consumed by the retriever. Every NCERT paragraph becomes **one
parent** (~1200 tokens) split into **2-4 children** (~300 tokens each).
Children get embedded and live in Pinecone; parents live in Supabase
and are joined back at retrieval time so the LLM sees full context
around the snippet that matched.

> **Why two tiers?** A 300-token child is small enough to embed
> precisely and to retrieve on a focused question, but is usually
> too small to answer from directly — it lacks surrounding
> definitions and worked-out steps. The 1200-token parent gives the
> generator enough surrounding context to write a coherent answer.
> This pattern is sometimes called "small-to-big" retrieval.

#### Worked example — Class 9 Physics, Chapter 10 (Force and Laws of Motion)

**Original textbook paragraph** (page 117):

> *Newton's second law of motion states that the rate of change of
> momentum of an object is directly proportional to the net external
> force applied on it. In equation form:*
>
> *$$\vec{F}_{net} = \frac{d\vec{p}}{dt}$$*
>
> *where $\vec{p} = m\vec{v}$ is the linear momentum. For constant
> mass, this simplifies to the well-known form:*
>
> *$$\vec{F}_{net} = m\vec{a}$$*
>
> *The direction of the force is the same as the direction of the
> change in momentum. The SI unit of force is the newton (N), defined
> as the force required to accelerate a 1 kg mass at 1 m/s². One
> newton equals $1 \text{ kg} \cdot \text{m/s}^2$.*

**Parent chunk** (stored in Supabase `parent_chunks` table, id `p_a1b2c3d4`):

```json
{
  "id": "p_a1b2c3d4",
  "chapter_key": "physics_9_ch10",
  "content": "Newton's second law of motion states that the rate of change of momentum of an object is directly proportional to the net external force applied on it. In equation form:\n\n$$\\vec{F}_{net} = \\frac{d\\vec{p}}{dt}$$\n\nwhere $\\vec{p} = m\\vec{v}$ is the linear momentum. For constant mass, this simplifies to the well-known form:\n\n$$\\vec{F}_{net} = m\\vec{a}$$\n\nThe direction of the force is the same as the direction of the change in momentum. The SI unit of force is the newton (N), defined as the force required to accelerate a 1 kg mass at 1 m/s². One newton equals $1 \\text{ kg} \\cdot \\text{m/s}^2$.",
  "token_count": 118,
  "content_type": "text",
  "metadata": {
    "page": 117,
    "section": "9.5 Newton's Second Law of Motion",
    "has_formula": true
  }
}
```

**Child chunks** (3 children, embedded and stored in Pinecone under
namespace `physics_9_ch10_force_and_laws_of_motion`):

```json
[
  {
    "id": "physics_9_ch10_0_a1b2c3d4",
    "values": [0.0123, -0.0456, ...],          // 1536-d OpenAI embedding
    "metadata": {
      "parent_id": "p_a1b2c3d4",
      "text": "Newton's second law of motion states that the rate of change of momentum of an object is directly proportional to the net external force applied on it. In equation form: $$\\vec{F}_{net} = \\frac{d\\vec{p}}{dt}$$",
      "chapter_key": "physics_9_ch10",
      "class_level": "9",
      "subject": "physics",
      "content_type": "text",
      "token_count": 51,
      "chunk_index": 0,
      "page": 117
    }
  },
  {
    "id": "physics_9_ch10_1_a1b2c3d4",
    "values": [-0.0234, 0.0567, ...],
    "metadata": {
      "parent_id": "p_a1b2c3d4",
      "text": "where $\\vec{p} = m\\vec{v}$ is the linear momentum. For constant mass, this simplifies to the well-known form: $$\\vec{F}_{net} = m\\vec{a}$$. The direction of the force is the same as the direction of the change in momentum.",
      "chapter_key": "physics_9_ch10",
      "class_level": "9",
      "subject": "physics",
      "content_type": "formula",
      "token_count": 48,
      "chunk_index": 1,
      "page": 117
    }
  },
  {
    "id": "physics_9_ch10_2_a1b2c3d4",
    "values": [0.0345, -0.0678, ...],
    "metadata": {
      "parent_id": "p_a1b2c3d4",
      "text": "The SI unit of force is the newton (N), defined as the force required to accelerate a 1 kg mass at 1 m/s². One newton equals $1 \\text{ kg} \\cdot \\text{m/s}^2$.",
      "chapter_key": "physics_9_ch10",
      "class_level": "9",
      "subject": "physics",
      "content_type": "definition",
      "token_count": 35,
      "chunk_index": 2,
      "page": 117
    }
  }
]
```

Key things to notice:

- **Chunk ID format**: `physics_9_ch10_0_a1b2c3d4` →
  `{chapter_key}_{chunk_index}_{parent_content_hash[:8]}`.
  Deterministic, so re-ingestion overwrites cleanly.
- **Children never split a formula** — the chunker detects `$...$` and
  `$$...$$` blocks and refuses to cut inside one.
- **Content type tagging** drives both retrieval (formula chunks
  surface for "what is the equation for…") and frontend rendering
  (formula chunks get a slightly different card).
- **Parent → child join**: when a child matches, the retriever swaps
  in the parent for the generator's context. The child text is what
  was matched; the parent text is what the LLM sees.

### Step D — Generate

`rag/generator.py` calls `gpt-4o-mini` in **streaming mode** with
`ANSWER_GENERATOR_PROMPT`, passing the reranked text chunks as context.

Diagram chunks are **stripped from the context** and sent to the
client as a separate SSE event after the stream completes. The
generator's prompt tells the model "Refer to the diagram below" so
the student expects a diagram to appear.

### Step E — Persist + cache

After streaming completes, the backend:
- Inserts a row in Supabase `chat_messages` (query, answer, sources, classification).
- Stores the full answer in Redis with key `edurag:ask:{hash}` for 1 hour.

### Streaming pipeline (end-to-end)

```
Browser  ──fetch()──▶  FastAPI  ──parallel──▶  classifier (gpt-4o-mini)
                              ──parallel──▶  embed query (text-embedding-3-small)
                              ──sse──▶  status: "Looking in Class 8 Science, Ch 4…"
                              ──sse──▶  retriever (Pinecone + BM25, RRF)
                              ──sse──▶  status: "Finding the most relevant sections…"
                              ──sse──▶  reranker (optional, Cohere)
                              ──sse──▶  status: "Reading through and writing your answer…"
                              ──sse──▶  generator (streams tokens)
                              ──sse──▶  diagram + sources events
                              ──sse──▶  done
```

**Measured latency** (Class 8 chapter 4, on a small 59-vector namespace):
- Cold (first request after idle): 5-10s time-to-first-token (Pinecone
  serverless cold start dominates)
- Warm: 3-3.5s time-to-first-token
- Full stream for a typical 200-token answer: 7-9s wall-clock (but the
  user sees tokens as they arrive, so perceived latency is the TTFT)

---

## 11. Vision / diagram processing (planned)

> **Status: not yet implemented.** Will be built in step 7
> (`backend/ingestion/diagram_processor.py`).
>
> **Note**: the current build uses **OpenAI gpt-4o-mini for everything
> (text + embeddings)**. Vision is a future addition — when added it
> will use a vision-capable model (likely `gpt-4o` or `gpt-4o-mini`
> with image input), not a separate model provider.

### Why vision matters

NCERT diagrams (ray diagrams, circuit diagrams, graphs, geometry
figures) are essential for understanding. The text chunk alone is
often meaningless without the figure. We need to:

1. Detect figures during PDF parsing.
2. Run a vision model on each figure to produce a **searchable
   description** (so a student asking "what is a convex lens" finds
   the ray diagram).
3. Upload the original image to Supabase Storage for inline display.
4. Embed the description (not the image) so the chunk is queryable.

### Planned flow (per diagram, during ingestion)

```
PDF page
  │
  ├─ PyMuPDF extracts embedded image + bbox + caption + 200 chars
  │  of surrounding text (before + after the figure)
  │
  ├─ DIAGRAM_DESCRIPTION_PROMPT is sent to a vision LLM
  │  with the image + caption + surrounding text + chapter context
  │
  │  Returns JSON:
  │  {
  │    "diagram_type": "ray diagram",
  │    "what_it_shows": "Light rays from a distant object passing through a convex lens",
  │    "components": ["lens", "principal axis", "focal points F1 and F2", "object", "image"],
  │    "concept_explained": "Image formation by a convex lens",
  │    "student_explanation": "A convex lens bends light rays toward a point called the focal point. When parallel rays from a distant object pass through, they converge to form a real, inverted image on the other side. ... ",
  │    "keywords": "convex lens, focal point, real image, ray diagram, light"
  │  }
  │
  ├─ The JSON `student_explanation` + `keywords` are concatenated
  │  and embedded as a "diagram chunk" in Pinecone
  │  (with metadata: content_type=diagram, page, bbox, supabase_url)
  │
  └─ The original PNG is uploaded to Supabase Storage at
     diagrams/{subject}/class_{level}/{chapter_slug}/fig_{page}_{hash}.png
     and the public URL is stored in the chunk metadata
```

### Retrieval-time behavior

When a student's question matches a diagram chunk:

1. The retriever returns it like any other chunk.
2. The generator **strips diagram chunks from the LLM context** — the
   LLM cannot read images anyway.
3. The generator's prompt says "Refer to the diagram below" so the
   student expects one.
4. After the text stream ends, the backend sends a `diagrams` SSE
   event with the public URLs and captions.
5. The frontend's `DiagramCard` component renders each image with
   its caption and the LLM's `student_explanation`.

### Why we delay vision for now

- `gpt-4o-mini` was selected for this build (per project owner
  decision). It supports image input, but we'll add vision as a
  separate ingestion-time concern rather than complicate the
  text-generation flow.
- Diagram processing is one of the most expensive ingestion steps.
- We want the rest of the pipeline stable first.

---

## 12. Dev mode vs Production mode

`DEV_MODE` is a single env flag. It currently has no behavioral effect
because all roles use `gpt-4o-mini` regardless, but the `MODELS` dict
in `settings.py` is wired so that flipping `DEV_MODE=false` can route
roles to more capable (and more expensive) models in one place.

When we're ready to upgrade, the swap will look like:

```python
# backend/config/settings.py
_PROD_MODELS = {
    "classifier": "gpt-4o-mini",     # keep cheap
    "answer":     "gpt-4o",          # upgrade for better answers
    "ingestion":  "gpt-4o",          # upgrade for better chunking/vision
    "vision":     "gpt-4o",          # vision-capable
}
```

And to switch: `DEV_MODE=false` in `.env`. No code changes needed.

---

## 13. Known limitations

- **No vision yet.** Diagram detection works at the PDF level (PyMuPDF
  finds embedded images), but the LLM description step is not
  implemented. The retriever can find diagram descriptions once they
  exist in Pinecone. The `diagram_processor.py` module has a clear
  seam where a `gpt-4o` (or similar) vision call can be inserted
  without changing the rest of the pipeline.
- **BM25 corpus is in-memory.** A re-deploy of the backend rebuilds
  the BM25 index for every namespace on first use. For 22 chapters
  this is fine, but if chapters get much larger, swap to a persistent
  sparse index (e.g. Pinecone's `sparse-dense` indexes).
- **No streaming cancellation.** If the browser closes the connection
  mid-stream, the backend keeps running the LLM call to completion.
  A future improvement: hook `request.is_disconnected()` into the
  generator's loop. (The frontend has a Stop button, but it only
  works before the LLM call starts.)
- **No multi-turn memory.** The /ask endpoint is stateless apart from
  the chat-history record. A follow-up question ("can you explain
  step 2?") gets no context from the previous turn.
- **Auth is email-only by default.** Google OAuth works once you
  configure it in the Supabase dashboard, but the frontend hides the
  Google button until then.
- **Single-region.** Pinecone is on `us-east-1`. Indian students will
  see ~200ms additional network latency. Can switch region if needed.
- **CORS is wide-open in dev.** Tighten before production.
- **No diagrams-storage pre-upload.** The `pdfs/` directory isn't
  volume-mounted into the backend container by default, so the
  `--upload-diagrams` ingest mode requires running the script
  outside the container (against the live Supabase + Pinecone).

---

## 14. Roadmap

**All 9 build steps done.** MVP is feature-complete for the
core RAG loop. Future work is below.

- [x] **Step 1**: `requirements.txt` + `package.json`
- [x] **Step 2**: `backend/config/constants.py` (NAMESPACE_MAP + prompts)
- [x] **Step 3**: `backend/config/settings.py` (OpenAI gpt-4o-mini)
- [x] **Step 4**: `backend/services/` (5 client wrappers)
- [x] **Step 5**: `backend/rag/` (classifier, retriever, reranker, generator with status SSE events)
- [x] **Step 6**: `backend/api/routes/` (query SSE, history, health)
- [x] **Step 7**: `backend/ingestion/` (parser, chunker, diagram processor, embedder, pipeline with incremental upsert)
- [x] **Step 8**: `frontend/` (Next.js 14, hooks, components, store, pages, Supabase Auth)
- [x] **Step 9**: `docker-compose.yml` + `scripts/` (ingest_chapter.py, ingest_all.py) + `Dockerfile` (backend + frontend) + README polish

### Future (after step 9)

- [ ] **Vision implementation** — `gpt-4o` vision calls in `diagram_processor.py` (~$0.15-0.25 for full 22-chapter ingest, see §11 for cost analysis)
- [ ] **Multi-turn conversations** — `conversation_id` + recent history prepended to the prompt
- [ ] **User auth** — Supabase Auth (email magic link ✅ done, Google OAuth is a 10-min setup)
- [ ] **Streaming cancellation** — `request.is_disconnected()` plumbing
- [ ] **Persistent sparse index** — Pinecone sparse-dense, or Qdrant
- [ ] **Evaluation harness** — RAGAS or custom metrics on a held-out NCERT QA set
- [ ] **Hindi + regional language support** — translation layer before generation
- [ ] **Mobile-responsive UI** — Tailwind breakpoints, KaTeX sizing
- [ ] **Rate limiting + abuse prevention** — per-user_id quota, Cloudflare Turnstile
- [ ] **Skip the classifier when pre-filter is set** — saves another 1.5-3s on warm path (currently the biggest remaining fixed cost)
- [ ] **Observability** — OpenTelemetry traces, structured logs to a dashboard

---

**Maintainer note**: This README is the canonical spec for EduRag.
Whenever we add or change a feature, update the relevant section here
in the same commit.
