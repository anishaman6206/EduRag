-- ─────────────────────────────────────────────────────────────────────────
-- EduRag Supabase schema
-- Run this once in the Supabase SQL editor (or via supabase-cli).
-- Idempotent: safe to re-run.
-- ─────────────────────────────────────────────────────────────────────────

-- Chat history: one row per (user, conversation, question, answer) exchange
create table if not exists public.chat_messages (
    id              uuid primary key default gen_random_uuid(),
    user_id         text not null,
    conversation_id text,                                 -- groups turns in one thread
    class_level     text,
    subject         text,
    chapter_key     text,
    query           text not null,
    answer          text not null,
    sources         jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists chat_messages_user_id_idx
    on public.chat_messages (user_id, created_at desc);

create index if not exists chat_messages_conversation_id_idx
    on public.chat_messages (conversation_id, created_at desc)
    where conversation_id is not null;


-- Parent chunks: 1200-token blocks stored in Postgres so the retriever
-- can swap them in for the LLM context at generation time.
create table if not exists public.parent_chunks (
    id            text primary key,                   -- p_<hash8>
    chapter_key   text not null,
    content       text not null,
    token_count   int not null,
    content_type  text not null,
    page_start    int,
    page_end      int,
    metadata      jsonb,
    created_at    timestamptz not null default now()
);

create index if not exists parent_chunks_chapter_key_idx
    on public.parent_chunks (chapter_key);


-- Storage bucket for diagram images.
-- Create the bucket in the Supabase dashboard:
--   Storage → New bucket → Name: diagrams → Public: ON
-- This is a one-time manual step. The ingestion pipeline uploads
-- to this bucket.
--
-- Path convention: {subject}/class_{level}/{chapter_key}/fig_{page}_{hash}.png
-- Example: physics/class_8/physics_8_ch4/fig_1_a1b2c3d4e5f6.png
