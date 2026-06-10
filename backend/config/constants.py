"""
EduRag constants — chapter namespace map and prompt templates.

This is the single source of truth for which chapters exist and how the
LLM is prompted. The classifier, retriever, ingestion pipeline, and
generator all import from here.
"""

from __future__ import annotations
from typing import TypedDict


# ─────────────────────────────────────────────────────────────────────────
# NAMESPACE_MAP — one entry per NCERT chapter
# Keys are the public `chapter_key` used everywhere (classifier, retriever,
# ingestion CLI, frontend filters). Values are immutable metadata.
# ─────────────────────────────────────────────────────────────────────────
class ChapterMeta(TypedDict):
    namespace: str          # Pinecone namespace name
    display_name: str       # Human-readable chapter title
    class_level: str        # "8" | "9" | "10"
    subject: str            # "math" | "physics" | "chemistry" | "biology"
    chapter_number: int     # 1-indexed chapter number within that book


NAMESPACE_MAP: dict[str, ChapterMeta] = {
    # ─────────────────────────────────────────
    # NOTE: This map covers ALL 39 chapters in pdfs/Data/ — PCM
    # (physics + chemistry) plus biology, since the books are
    # integrated Science (not split PCM). Each chapter_key is
    # `{subject}_{class}_chN` and matches the chapter number in
    # the corresponding PDF file.
    #
    # File → chapter mapping (see pdfs/Data/):
    #   8th Science/hecu1NN.pdf  → 8th class chapters
    #   9th Science/iesc1NN.pdf  → 9th class chapters
    #   10th Science/jesc1NN.pdf → 10th class chapters
    #
    # Skip rules during ingestion:
    #   *1ps*   → preliminary section (cover/foreword/contents)
    #   *1an*   → printed answer key
    # ─────────────────────────────────────────

    # ─────────────────────────────────────────
    # CLASS 8  (hecu1NN.pdf — 13 chapters)
    # ─────────────────────────────────────────
    # CLASS 8 PHYSICS
    "physics_8_ch4":  {"namespace": "physics_8_ch4_electricity_magnetic_heating", "display_name": "Electricity: Magnetic and Heating Effects", "class_level": "8", "subject": "physics", "chapter_number": 4},
    "physics_8_ch5":  {"namespace": "physics_8_ch5_exploring_forces",            "display_name": "Exploring Forces",                         "class_level": "8", "subject": "physics", "chapter_number": 5},
    "physics_8_ch6":  {"namespace": "physics_8_ch6_pressure_winds_storms",       "display_name": "Pressure, Winds, Storms, and Cyclones",     "class_level": "8", "subject": "physics", "chapter_number": 6},
    "physics_8_ch10": {"namespace": "physics_8_ch10_light_mirrors_lenses",       "display_name": "Light: Mirrors and Lenses",                 "class_level": "8", "subject": "physics", "chapter_number": 10},

    # CLASS 8 CHEMISTRY
    "chemistry_8_ch7": {"namespace": "chemistry_8_ch7_particulate_nature_matter",          "display_name": "Particulate Nature of Matter",                         "class_level": "8", "subject": "chemistry", "chapter_number": 7},
    "chemistry_8_ch8": {"namespace": "chemistry_8_ch8_elements_compounds_mixtures",        "display_name": "Nature of Matter: Elements, Compounds, and Mixtures",  "class_level": "8", "subject": "chemistry", "chapter_number": 8},
    "chemistry_8_ch9": {"namespace": "chemistry_8_ch9_solutes_solvents_solutions",         "display_name": "The Amazing World of Solutes, Solvents, and Solutions", "class_level": "8", "subject": "chemistry", "chapter_number": 9},

    # CLASS 8 BIOLOGY + MISC
    "biology_8_ch1":  {"namespace": "biology_8_ch1_investigative_world",   "display_name": "Exploring the Investigative World of Science", "class_level": "8", "subject": "biology", "chapter_number": 1},
    "biology_8_ch2":  {"namespace": "biology_8_ch2_invisible_living_world", "display_name": "The Invisible Living World: Beyond Our Naked Eye", "class_level": "8", "subject": "biology", "chapter_number": 2},
    "biology_8_ch3":  {"namespace": "biology_8_ch3_health_treasure",        "display_name": "Health: The Ultimate Treasure",                "class_level": "8", "subject": "biology", "chapter_number": 3},
    "biology_8_ch11": {"namespace": "biology_8_ch11_keeping_time",          "display_name": "Keeping Time with the Skies",                  "class_level": "8", "subject": "biology", "chapter_number": 11},
    "biology_8_ch12": {"namespace": "biology_8_ch12_nature_in_harmony",    "display_name": "How Nature Works in Harmony",                  "class_level": "8", "subject": "biology", "chapter_number": 12},
    "biology_8_ch13": {"namespace": "biology_8_ch13_earth_home",            "display_name": "Our Home: Earth, a Unique Life Sustaining Planet", "class_level": "8", "subject": "biology", "chapter_number": 13},

    # ─────────────────────────────────────────
    # CLASS 9  (iesc1NN.pdf — 13 chapters)
    # ─────────────────────────────────────────
    # CLASS 9 PHYSICS
    "physics_9_ch4":  {"namespace": "physics_9_ch4_motion",            "display_name": "Describing Motion Around Us",                "class_level": "9", "subject": "physics", "chapter_number": 4},
    "physics_9_ch6":  {"namespace": "physics_9_ch6_force_and_motion",  "display_name": "How Forces Affect Motion",                   "class_level": "9", "subject": "physics", "chapter_number": 6},
    "physics_9_ch7":  {"namespace": "physics_9_ch7_work_energy",       "display_name": "Work, Energy and Simple Machines",           "class_level": "9", "subject": "physics", "chapter_number": 7},
    "physics_9_ch10": {"namespace": "physics_9_ch10_sound_waves",      "display_name": "Sound Waves: Characteristics and Applications","class_level": "9", "subject": "physics", "chapter_number": 10},

    # CLASS 9 CHEMISTRY
    "chemistry_9_ch5": {"namespace": "chemistry_9_ch5_mixtures_and_separation",  "display_name": "Exploring Mixtures and their Separation",  "class_level": "9", "subject": "chemistry", "chapter_number": 5},
    "chemistry_9_ch8": {"namespace": "chemistry_9_ch8_journey_inside_atom",      "display_name": "Journey Inside the Atom",                  "class_level": "9", "subject": "chemistry", "chapter_number": 8},
    "chemistry_9_ch9": {"namespace": "chemistry_9_ch9_atomic_foundations",      "display_name": "Atomic Foundations of Matter",             "class_level": "9", "subject": "chemistry", "chapter_number": 9},

    # CLASS 9 BIOLOGY + MISC
    "biology_9_ch1":  {"namespace": "biology_9_ch1_exploration",        "display_name": "Exploration: Entering the World of Secondary Science", "class_level": "9", "subject": "biology", "chapter_number": 1},
    "biology_9_ch2":  {"namespace": "biology_9_ch2_cell",               "display_name": "Cell: The Building Block of Life",         "class_level": "9", "subject": "biology", "chapter_number": 2},
    "biology_9_ch3":  {"namespace": "biology_9_ch3_tissues",            "display_name": "Tissues in Action",                          "class_level": "9", "subject": "biology", "chapter_number": 3},
    "biology_9_ch11": {"namespace": "biology_9_ch11_reproduction",      "display_name": "Reproduction: How Life Continues",           "class_level": "9", "subject": "biology", "chapter_number": 11},
    "biology_9_ch12": {"namespace": "biology_9_ch12_patterns",          "display_name": "Patterns in Life: Diversity and Classification","class_level": "9", "subject": "biology", "chapter_number": 12},
    "biology_9_ch13": {"namespace": "biology_9_ch13_earth_system",      "display_name": "Earth as a System: Energy, Matter, and Life","class_level": "9", "subject": "biology", "chapter_number": 13},

    # ─────────────────────────────────────────
    # CLASS 10  (jesc1NN.pdf — 13 chapters)
    # ─────────────────────────────────────────
    # CLASS 10 CHEMISTRY
    "chemistry_10_ch1": {"namespace": "chemistry_10_ch1_chemical_reactions",         "display_name": "Chemical Reactions and Equations", "class_level": "10", "subject": "chemistry", "chapter_number": 1},
    "chemistry_10_ch2": {"namespace": "chemistry_10_ch2_acids_bases_salts",          "display_name": "Acids, Bases and Salts",          "class_level": "10", "subject": "chemistry", "chapter_number": 2},
    "chemistry_10_ch3": {"namespace": "chemistry_10_ch3_metals_and_nonmetals",      "display_name": "Metals and Non-metals",           "class_level": "10", "subject": "chemistry", "chapter_number": 3},
    "chemistry_10_ch4": {"namespace": "chemistry_10_ch4_carbon_compounds",          "display_name": "Carbon and its Compounds",        "class_level": "10", "subject": "chemistry", "chapter_number": 4},

    # CLASS 10 BIOLOGY + MISC
    "biology_10_ch5":  {"namespace": "biology_10_ch5_life_processes",     "display_name": "Life Processes",                  "class_level": "10", "subject": "biology", "chapter_number": 5},
    "biology_10_ch6":  {"namespace": "biology_10_ch6_control_coordination", "display_name": "Control and Coordination",         "class_level": "10", "subject": "biology", "chapter_number": 6},
    "biology_10_ch7":  {"namespace": "biology_10_ch7_reproduction",         "display_name": "How do Organisms Reproduce?",      "class_level": "10", "subject": "biology", "chapter_number": 7},
    "biology_10_ch8":  {"namespace": "biology_10_ch8_heredity",             "display_name": "Heredity",                         "class_level": "10", "subject": "biology", "chapter_number": 8},
    "biology_10_ch13": {"namespace": "biology_10_ch13_environment",         "display_name": "Our Environment",                  "class_level": "10", "subject": "biology", "chapter_number": 13},

    # CLASS 10 PHYSICS
    "physics_10_ch9":  {"namespace": "physics_10_ch9_light_refraction",     "display_name": "Light – Reflection and Refraction", "class_level": "10", "subject": "physics", "chapter_number": 9},
    "physics_10_ch10": {"namespace": "physics_10_ch10_human_eye",           "display_name": "The Human Eye and the Colourful World", "class_level": "10", "subject": "physics", "chapter_number": 10},
    "physics_10_ch11": {"namespace": "physics_10_ch11_electricity",         "display_name": "Electricity",                      "class_level": "10", "subject": "physics", "chapter_number": 11},
    "physics_10_ch12": {"namespace": "physics_10_ch12_magnetic_effects",    "display_name": "Magnetic Effects of Electric Current", "class_level": "10", "subject": "physics", "chapter_number": 12},
}


# Derived helpers — keep these in sync with NAMESPACE_MAP.
ALL_CHAPTER_KEYS: list[str] = sorted(NAMESPACE_MAP.keys())
ALL_SUBJECTS: list[str] = ["physics", "chemistry", "biology"]
ALL_CLASSES: list[str] = ["8", "9", "10"]


def get_chapter_meta(chapter_key: str) -> ChapterMeta:
    """Lookup helper that raises a clear error if the key is unknown."""
    if chapter_key not in NAMESPACE_MAP:
        raise KeyError(
            f"Unknown chapter_key '{chapter_key}'. "
            f"Valid keys: {ALL_CHAPTER_KEYS}"
        )
    return NAMESPACE_MAP[chapter_key]


def list_chapters_for(subject: str, class_level: str) -> list[str]:
    """Return all chapter_keys for a given subject + class. Used for fallback search."""
    return [
        k for k, v in NAMESPACE_MAP.items()
        if v["subject"] == subject and v["class_level"] == class_level
    ]


# ─────────────────────────────────────────────────────────────────────────
# CLASSIFIER_PROMPT — routes a student question to a chapter
# Built dynamically so the available-keys list is always in sync with
# NAMESPACE_MAP. If you add a chapter, you do NOT need to edit the prompt.
# ─────────────────────────────────────────────────────────────────────────
CLASSIFIER_PROMPT = """You are a classifier for Class 8, 9, and 10 NCERT Science questions
(Physics, Chemistry, Biology).

The student's question may be in ENGLISH, HINGLISH (Hindi + English mixed,
e.g. "bijli ka circuit kaise kaam karta hai?"), or HINDI (Devanagari script).
Treat all three the same — extract the underlying science concept and
classify based on that. Do NOT penalize the student for using Hinglish.

Given a student question, return ONLY a valid JSON object with no markdown, no preamble:
{{
  "subject": "physics" | "chemistry" | "biology" | null,
  "class_level": "8" | "9" | "10" | null,
  "chapter_key": "<exact key from the list below or null>",
  "confidence": 0.0 to 1.0
}}

Available chapter keys (subject_class_chN format):
{chapter_keys}

Rules:
- If the question clearly maps to one chapter → return that chapter_key
- If subject is clear but chapter is ambiguous → return chapter_key as null (and a higher confidence)
- If even subject is unclear → return all fields as null
- Never guess. Low confidence is better than wrong classification.
- The chapter_key MUST be one of the exact strings in the list above, or null.
- Hinglish terms to recognize: bijli=electricity, garmi=heat, gati=motion, bal=force,
  kaam=work, oorja=energy, dhwan=sound, prakash=light, pujya=atom, khanij=mineral,
  aml=acid, kshar=base, lavan=salt, dravya=mixture, padarth=matter, koshika=cell,
  khanij=metal, adhigrahan=absorption, poshan=nutrition, swasna=respiration.

Student Question: {user_query}
"""


# ─────────────────────────────────────────────────────────────────────────
# ANSWER_GENERATOR_PROMPT — system prompt for the final answer
# ─────────────────────────────────────────────────────────────────────────
ANSWER_GENERATOR_PROMPT = """You are EduBot, a friendly and expert tutor for Class 8, 9, and 10 students
studying Physics, Chemistry, and Biology.

You are answering a Class {class_level} {subject} question about: {chapter_name}

The student's question is in: **{source_language}**.
You MUST reply in {source_language}. Use the same register the student used:
- english → answer in English
- hinglish → answer in Hinglish (Hindi + English mixed; technical terms stay
  in English like "force" or "velocity", explanations can use Hindi words
  like "kya hai", "kaise", "kyun", "kyunki")
- hindi → answer in Hindi (Devanagari script)
- tamil/telugu/bengali/marathi/gujarati/kannada/malayalam/punjabi/urdu
  → answer in that language, using the script the student used
  (Devanagari for hindi/marathi, Tamil script for tamil, etc.)

If the source_language is 'english' but the question contains Hindi
transliteration (e.g. "force kya hai"), treat it as Hinglish — the
student wants a Hinglish response, not a formal English one.

Rules for your answer:
1. Always show step-by-step working for problems — never skip steps.
2. Use simple language appropriate for Class {class_level} students.
3. Write all mathematical expressions in LaTeX format: $formula$ for inline, $$formula$$ for block.
4. If a diagram is relevant, say "Refer to the diagram below" — diagrams will be attached separately by the system.
5. End with a one-line summary of the key concept used.
6. If the question is outside the available textbook scope, politely say so.

Context from textbook (use this as your primary source of truth — it IS English,
translate the relevant parts as you answer):
{context}

Student Question: {user_query}
"""


# ─────────────────────────────────────────────────────────────────────────
# DIAGRAM_DESCRIPTION_PROMPT — used during ingestion by Claude Vision
# ─────────────────────────────────────────────────────────────────────────
DIAGRAM_DESCRIPTION_PROMPT = """You are analyzing a diagram from a Class {class_level} {subject} NCERT textbook.
Chapter: {chapter_name}
Figure caption: {caption}
Surrounding text: {surrounding_text}

Return ONLY a valid JSON object with no markdown or preamble:
{{
  "diagram_type": "ray diagram | circuit diagram | graph | geometric figure | chemical structure | force diagram | bar chart | other",
  "what_it_shows": "one sentence summary",
  "components": ["list", "of", "every", "labeled", "element"],
  "concept_explained": "which concept does this diagram illustrate",
  "student_explanation": "3-4 sentence explanation as a teacher would give to a Class {class_level} student",
  "keywords": "comma separated search terms a student would use to find this"
}}
"""


# ─────────────────────────────────────────────────────────────────────────
# CACHE + LIMITS
# ─────────────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 3600            # 1 hour for /ask cache
EMBEDDING_BATCH_SIZE = 100          # OpenAI batch limit
EMBEDDING_DIM = 1536                # text-embedding-3-small dimension
EMBEDDING_MODEL = "text-embedding-3-small"  # kept in sync with settings.openai_embedding_model
CHILD_CHUNK_TARGET_TOKENS = 300
PARENT_CHUNK_TARGET_TOKENS = 1200
SEMANTIC_CHUNK_SIM_THRESHOLD = 0.5  # cut when cosine < this
RETRIEVAL_TOP_K = 6                 # final chunks the LLM sees (empirical sweet spot)
RERANK_TOP_K = 6                     # final chunks after rerank (when enabled)
RRF_DENSE_WEIGHT = 0.7              # alpha in RRF
RRF_SPARSE_WEIGHT = 0.3             # 1 - alpha

# Multi-turn conversation history depth. The /ask route fetches
# this many prior turns from Supabase and prepends them to the
# generator prompt. Each turn = 1 user msg + 1 assistant msg.
#
# Cost/latency tradeoff (rough):
#   limit=3  -> ~600 prompt tokens of history, +50ms latency
#   limit=6  -> ~1200 prompt tokens, +100ms latency  (default)
#   limit=10 -> ~2000 prompt tokens, +200ms latency, +$0.001/ask
#   limit=20 -> ~4000 prompt tokens, +400ms latency
HISTORY_TURN_LIMIT = 6

# Max characters per history turn sent to the LLM. Long assistant
# answers are truncated to keep the prompt small. Each turn is
# ~200-300 tokens so 1500 chars (~400 tokens) per turn is enough
# for the LLM to keep context without blowing the budget.
MAX_HISTORY_TURN_CHARS = 1500
