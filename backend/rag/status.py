"""
Status messages for the RAG pipeline.

These are short, friendly, human-readable strings sent as SSE events
BEFORE the heavy work of each phase, so the user sees something
happening instead of staring at a blank box. The first token from
gpt-4o-mini typically arrives in 400-600ms; status events fill the
gap from "submit" to "first token".

Why a separate module:
- The strings are user-facing copy that may need translation later.
  Centralizing them in one place is the difference between a single
  edit and hunting through code.
- The status events are emitted from inside the retriever /
  classifier / generator; threading a callback through each of
  those would be noisy. A module-level "current emitter" is cleaner.
"""

from __future__ import annotations
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# The current SSE emitter. The route handler sets this at the start
# of each /ask request, and the pipeline modules (classifier,
# retriever, generator) call it at each phase boundary.
#
# Signature: async (status_message: str) -> None
# The emitter should yield an SSE event with type="status" to the
# client. The route's emitter does that.
StatusEmitter = Optional[Callable[[str], Awaitable[None]]]

_current_emitter: StatusEmitter = None


def set_status_emitter(emitter: StatusEmitter) -> None:
    """
    Register an emitter for the current request. Called by the route
    handler at the start of /ask. Pass None to clear.
    """
    global _current_emitter
    _current_emitter = emitter


def get_status_emitter() -> StatusEmitter:
    """Return the currently-registered emitter (or None)."""
    return _current_emitter


# ─────────────────────────────────────────────────────────────────────────
# Status message templates
# ─────────────────────────────────────────────────────────────────────────
def _book_label_for_class(class_level: str | None) -> str:
    """Map '8' / '9' / '10' to a friendly label."""
    mapping = {
        "7":  "Class 7",
        "8":  "Class 8 Science",
        "9":  "Class 9 Science",
        "10": "Class 10 Science",
    }
    return mapping.get(class_level or "", "your textbook")


# Phases that fire as status events during /ask, in order
PHASE_THINKING   = "thinking"      # initial — before classifier
PHASE_LOOKING_UP = "looking_up"    # classifier done
PHASE_SEARCHING  = "searching"     # retriever running
PHASE_RERANKING  = "reranking"     # optional rerank
PHASE_READING    = "reading"       # LLM starting
PHASE_DONE       = "done"


def thinking_message(query: str) -> str:
    """First thing the user sees after they submit. ~50ms latency."""
    # Truncate the query to keep the message short
    short = (query[:60] + "…") if len(query) > 60 else query
    return f"Thinking about \"{short}\"…"


def looking_up_message(classification) -> str:
    """
    After the classifier returns. Tells the user which book we
    think the question belongs to. ~300-500ms after thinking.
    """
    book = _book_label_for_class(classification.class_level)
    if classification.chapter_meta:
        ch_num = classification.chapter_meta["chapter_number"]
        ch_name = classification.chapter_meta["display_name"]
        return f"Looking in {book}, Chapter {ch_num}: {ch_name}…"
    if classification.subject and classification.class_level:
        return f"Looking through {book} to find the right chapter…"
    return f"Looking through your textbooks…"


def searching_message() -> str:
    """While the retriever is running (~50-150ms)."""
    return "Finding the most relevant sections…"


def reranking_message() -> str:
    """Only fires if Cohere is enabled (~100-200ms)."""
    return "Re-ordering results for the best match…"


def reading_message() -> str:
    """Once we have context and the LLM is about to start streaming."""
    return "Reading through and writing your answer…"


def done_message() -> str:
    """Final status before the `done` event."""
    return "All done!"
