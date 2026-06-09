"""
Query classifier.

Takes a student's free-form question and routes it to the most likely
NCERT chapter. Uses gpt-4o-mini in JSON mode with CLASSIFIER_PROMPT.

Failure modes handled:
- Bad JSON from the model → parse fallback (strip markdown fences,
  retry once, then give up).
- Network/timeout errors → 3 retries with exponential backoff
  (1s, 2s, 4s) using tenacity.
- All retries fail → return a "null" classification. The caller
  (retriever) then falls back to a broad search across all chapters
  of whatever subject+class the user hinted at, or all of PCM if
  even that's missing.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass

from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

from config.constants import (
    CLASSIFIER_PROMPT, NAMESPACE_MAP, ALL_CHAPTER_KEYS, ChapterMeta,
)
from services.openai_service import complete_chat_json

logger = logging.getLogger(__name__)


@dataclass
class Classification:
    """Result of routing a student question to a chapter."""
    subject: str | None          # "math" | "physics" | "chemistry" | None
    class_level: str | None      # "7" | "8" | "9" | None
    chapter_key: str | None      # exact key from NAMESPACE_MAP, or None
    confidence: float            # 0.0 - 1.0
    chapter_meta: ChapterMeta | None  # resolved metadata if chapter_key is set

    @property
    def is_fully_resolved(self) -> bool:
        """True iff the model gave us a chapter we trust enough to search."""
        return (
            self.chapter_key is not None
            and self.chapter_key in NAMESPACE_MAP
            and self.confidence >= 0.5
        )

    @property
    def fallback_chapter_keys(self) -> list[str]:
        """
        Chapters to search if the model didn't pick one (or picked
        one we don't trust). If subject+class are known, return all
        chapters of that pair. Otherwise return everything.
        """
        if self.subject and self.class_level:
            return [
                k for k, v in NAMESPACE_MAP.items()
                if v["subject"] == self.subject and v["class_level"] == self.class_level
            ]
        return list(NAMESPACE_MAP.keys())


def _parse_model_json(raw: str) -> dict:
    """
    Defensive JSON parse. The model is told to return JSON only, but
    occasionally it wraps the answer in ```json ... ``` fences. Strip
    those, then json.loads. Raise ValueError on failure so the retry
    decorator kicks in.
    """
    text = raw.strip()

    # Strip markdown code fences if the model added them
    if text.startswith("```"):
        # Remove the first line (```json or ```) and the trailing fence
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return json.loads(text)


def _coerce_classification(parsed: dict) -> Classification:
    """Validate the parsed JSON and build a Classification."""
    subject = parsed.get("subject")
    class_level = parsed.get("class_level")
    chapter_key = parsed.get("chapter_key")
    confidence = parsed.get("confidence", 0.0)

    # Normalize: nulls / wrong types all become None
    if subject not in (None, "math", "physics", "chemistry"):
        subject = None
    if class_level not in (None, "7", "8", "9"):
        class_level = None
    if chapter_key not in ALL_CHAPTER_KEYS:
        chapter_key = None
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    chapter_meta = NAMESPACE_MAP[chapter_key] if chapter_key else None

    # Cross-check: if chapter is set, subject/class must agree with it
    if chapter_meta is not None:
        if subject and subject != chapter_meta["subject"]:
            logger.warning(
                "Classifier mismatch: chapter %s expects subject %s, got %s — keeping chapter",
                chapter_key, chapter_meta["subject"], subject,
            )
        if class_level and class_level != chapter_meta["class_level"]:
            logger.warning(
                "Classifier mismatch: chapter %s expects class %s, got %s — nulling chapter",
                chapter_key, chapter_meta["class_level"], class_level,
            )
            chapter_key = None
            chapter_meta = None

    return Classification(
        subject=subject,
        class_level=class_level,
        chapter_key=chapter_key,
        confidence=confidence,
        chapter_meta=chapter_meta,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),  # 1s, 2s, 4s
    retry=retry_if_exception_type((ValueError, json.JSONDecodeError, RuntimeError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _classify_once(query: str, *, hint_subject: str | None, hint_class: str | None) -> str:
    """
    One attempt at classification. Returns the raw model text. The
    retry decorator handles transient errors with exponential backoff.
    """
    # Build the prompt with the dynamic chapter-key list baked in
    prompt = CLASSIFIER_PROMPT.format(
        chapter_keys=", ".join(ALL_CHAPTER_KEYS),
        user_query=query,
    )

    # The system prompt reinforces "JSON only" because OpenAI's JSON
    # mode still needs the model to be told what shape to output.
    system = (
        "You are a strict JSON-producing classifier. "
        "Reply with one valid JSON object and nothing else — no prose, "
        "no markdown fences, no explanation. "
        f"Allowed subjects: math, physics, chemistry. "
        f"Allowed class levels: 7, 8, 9. "
        f"chapter_key must be from the provided list or null. "
        f"confidence is a float between 0 and 1."
    )

    # If the user pre-filtered by subject/class, fold that into the user
    # message so the model is more likely to agree.
    user_addendum = ""
    if hint_subject:
        user_addendum += f"\n\nHint: the student is studying {hint_subject}."
    if hint_class:
        user_addendum += f"\n\nHint: the student is in class {hint_class}."

    return await complete_chat_json(
        role="classifier",
        system=system,
        user=prompt + user_addendum,
        max_tokens=200,
        temperature=0.0,  # deterministic — same input → same chapter
    )


async def classify_query(
    query: str,
    *,
    hint_subject: str | None = None,
    hint_class: str | None = None,
) -> Classification:
    """
    Classify a student question. Returns a Classification even on
    total failure (all fields None, confidence 0) so the caller can
    fall back to broad search without special-casing exceptions.

    Args:
        query: The student's free-form question.
        hint_subject: Optional pre-filter from the UI ("physics" etc).
                      Folded into the prompt so the classifier agrees
                      with the user's explicit filter.
        hint_class: Optional pre-filter ("7" | "8" | "9").

    Returns:
        Classification with subject, class_level, chapter_key,
        confidence, and the resolved chapter metadata.
    """
    try:
        raw = await _classify_once(query, hint_subject=hint_subject, hint_class=hint_class)
        parsed = _parse_model_json(raw)
        classification = _coerce_classification(parsed)
        logger.info(
            "Classified query=%r → subject=%s class=%s chapter=%s confidence=%.2f",
            query[:80], classification.subject, classification.class_level,
            classification.chapter_key, classification.confidence,
        )
        return classification
    except Exception as e:
        # All retries exhausted. Return a null classification so the
        # retriever does a broad search.
        logger.error("Classification failed after retries: %s", e)
        return Classification(
            subject=hint_subject,
            class_level=hint_class,
            chapter_key=None,
            confidence=0.0,
            chapter_meta=None,
        )
