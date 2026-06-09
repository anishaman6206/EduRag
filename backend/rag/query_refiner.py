"""
Query refiner.

Takes a student question (which may be in English, Hinglish, or
Hindi) and produces:
  1. A clean English version for the dense retriever to embed
     and search. This is the BIGGEST win — multilingual queries
     match poorly against the English NCERT corpus without
     translation.
  2. A language tag so the answer generator can reply in the
     student's source language (e.g. Hinglish in -> Hinglish out).

The refiner is a small, fast gpt-4o-mini call (max 200 tokens,
~300-500ms typical). With the embedding cache on the result
vector, this is a one-time cost per unique query.

Why a separate LLM call instead of just using the existing
classifier? Because the refiner is a no-decisions translation
task — the classifier is a routing task. They have different
optimal prompts. We could merge them later but the separation
is cleaner for now.
"""

from __future__ import annotations
import json
import logging
from typing import NamedTuple

from services.openai_service import complete_chat_json

logger = logging.getLogger(__name__)


# A small set of canonical language tags the answer prompt can
# branch on. Anything not in this list falls back to English.
SUPPORTED_LANGUAGES = (
    "english",
    "hinglish",
    "hindi",
    "tamil",
    "telugu",
    "bengali",
    "marathi",
    "gujarati",
    "kannada",
    "malayalam",
    "punjabi",
    "urdu",
)


class RefinedQuery(NamedTuple):
    english: str               # the cleaned, English-only version
    original_language: str      # e.g. "hinglish", "hindi", "english"
    original: str               # the user's original (untouched) query


_REFINE_PROMPT = """You are a query translator for an Indian school tutoring app.
Students ask questions in English, Hinglish (Hindi + English mixed), or pure
Hindi (Devanagari). Your job: produce a CLEAN ENGLISH VERSION of the
question that will be used for semantic search against an English
NCERT textbook corpus. Also identify the source language so the
answer can be in the same register.

Return ONLY a valid JSON object, no markdown, no preamble:
{
  "english": "<the question rewritten as a clean English query that an English search engine would handle well>",
  "language": "<one of: english, hinglish, hindi, tamil, telugu, bengali, marathi, gujarati, kannada, malayalam, punjabi, urdu>"
}

Translation rules:
- Preserve the science concept EXACTLY. Don't change what's being asked.
- For technical terms, keep the English word (e.g. "force", "velocity").
  These match the textbook.
- If the student said "bijli", translate to "electricity" — NOT keep
  the Hindi word.
- Expand abbreviations (e.g. "pH" stays "pH", but "F=ma" should
  become "Newton's second law F=ma").
- Keep the question's complexity. Don't simplify a Class 10
  question into a Class 5 question.
- If the question is already in English, set language="english"
  and return the original question in english.
- If the question is a mix (Hinglish), set language="hinglish".
- If the question is pure Hindi (Devanagari), set language="hindi".
- If unsure, default language="english".

Student question: """


async def refine_query(query: str) -> RefinedQuery:
    """
    Translate a multilingual query to clean English and tag the source
    language. Returns the original (unrefined) query unchanged so the
    answer generator can still see what the student actually asked.

    Always runs (no skip heuristic). The cost is one gpt-4o-mini
    JSON-mode call with max_tokens=200 — typically 300-500ms. Worth
    it because:
      - Hinglish/Hindi queries match poorly against an English corpus
        without translation
      - Misspelled queries (very common with students) get fixed here
      - The result is a clean English query that the dense retriever
        can embed accurately
    """
    try:
        raw = await complete_chat_json(
            role="answer",  # same model as the answer generator
            system=(
                "You translate student questions into clean English and "
                "tag the source language. Always reply with one valid "
                "JSON object. No prose, no markdown."
            ),
            user=_REFINE_PROMPT + query,
            max_tokens=200,
            temperature=0.0,
        )
        parsed = json.loads(raw)
        english = str(parsed.get("english", "")).strip() or query
        language = str(parsed.get("language", "english")).strip().lower()
        if language not in SUPPORTED_LANGUAGES:
            language = "english"
        return RefinedQuery(
            english=english,
            original_language=language,
            original=query,
        )
    except Exception as e:
        # Refiner failure should never break the pipeline. Fall back
        # to the original query as English.
        logger.warning("Query refinement failed: %s", e)
        return RefinedQuery(
            english=query,
            original_language="english",
            original=query,
        )
