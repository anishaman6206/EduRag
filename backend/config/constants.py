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
    class_level: str        # "7" | "8" | "9"
    subject: str            # "math" | "physics" | "chemistry"
    chapter_number: int     # 1-indexed chapter number within that book


NAMESPACE_MAP: dict[str, ChapterMeta] = {

    # ─────────────────────────────────────────
    # MATHEMATICS
    # ─────────────────────────────────────────
    # CLASS 7 MATHEMATICS
    "math_7_ch1":  {"namespace": "math_7_ch1_integers",                    "display_name": "Integers",                            "class_level": "7", "subject": "math", "chapter_number": 1},
    "math_7_ch2":  {"namespace": "math_7_ch2_fractions_and_decimals",      "display_name": "Fractions and Decimals",              "class_level": "7", "subject": "math", "chapter_number": 2},
    "math_7_ch3":  {"namespace": "math_7_ch3_data_handling",               "display_name": "Data Handling",                       "class_level": "7", "subject": "math", "chapter_number": 3},
    "math_7_ch4":  {"namespace": "math_7_ch4_simple_equations",            "display_name": "Simple Equations",                    "class_level": "7", "subject": "math", "chapter_number": 4},
    "math_7_ch5":  {"namespace": "math_7_ch5_lines_and_angles",            "display_name": "Lines and Angles",                    "class_level": "7", "subject": "math", "chapter_number": 5},
    "math_7_ch6":  {"namespace": "math_7_ch6_triangle_and_properties",     "display_name": "The Triangle and its Properties",     "class_level": "7", "subject": "math", "chapter_number": 6},
    "math_7_ch7":  {"namespace": "math_7_ch7_comparing_quantities",        "display_name": "Comparing Quantities",                "class_level": "7", "subject": "math", "chapter_number": 7},
    "math_7_ch8":  {"namespace": "math_7_ch8_rational_numbers",            "display_name": "Rational Numbers",                    "class_level": "7", "subject": "math", "chapter_number": 8},
    "math_7_ch9":  {"namespace": "math_7_ch9_perimeter_and_area",          "display_name": "Perimeter and Area",                  "class_level": "7", "subject": "math", "chapter_number": 9},
    "math_7_ch10": {"namespace": "math_7_ch10_algebraic_expressions",      "display_name": "Algebraic Expressions",               "class_level": "7", "subject": "math", "chapter_number": 10},
    "math_7_ch11": {"namespace": "math_7_ch11_exponents_and_powers",       "display_name": "Exponents and Powers",                "class_level": "7", "subject": "math", "chapter_number": 11},
    "math_7_ch12": {"namespace": "math_7_ch12_symmetry",                   "display_name": "Symmetry",                            "class_level": "7", "subject": "math", "chapter_number": 12},
    "math_7_ch13": {"namespace": "math_7_ch13_visualising_solid_shapes",   "display_name": "Visualising Solid Shapes",            "class_level": "7", "subject": "math", "chapter_number": 13},

    # CLASS 8 MATHEMATICS
    "math_8_ch1":  {"namespace": "math_8_ch1_rational_numbers",                     "display_name": "Rational Numbers",                        "class_level": "8", "subject": "math", "chapter_number": 1},
    "math_8_ch2":  {"namespace": "math_8_ch2_linear_equations_one_variable",        "display_name": "Linear Equations in One Variable",        "class_level": "8", "subject": "math", "chapter_number": 2},
    "math_8_ch3":  {"namespace": "math_8_ch3_understanding_quadrilaterals",         "display_name": "Understanding Quadrilaterals",             "class_level": "8", "subject": "math", "chapter_number": 3},
    "math_8_ch4":  {"namespace": "math_8_ch4_data_handling",                        "display_name": "Data Handling",                           "class_level": "8", "subject": "math", "chapter_number": 4},
    "math_8_ch5":  {"namespace": "math_8_ch5_squares_and_square_roots",             "display_name": "Squares and Square Roots",                "class_level": "8", "subject": "math", "chapter_number": 5},
    "math_8_ch6":  {"namespace": "math_8_ch6_cubes_and_cube_roots",                 "display_name": "Cubes and Cube Roots",                    "class_level": "8", "subject": "math", "chapter_number": 6},
    "math_8_ch7":  {"namespace": "math_8_ch7_comparing_quantities",                 "display_name": "Comparing Quantities",                    "class_level": "8", "subject": "math", "chapter_number": 7},
    "math_8_ch8":  {"namespace": "math_8_ch8_algebraic_expressions_and_identities", "display_name": "Algebraic Expressions and Identities",    "class_level": "8", "subject": "math", "chapter_number": 8},
    "math_8_ch9":  {"namespace": "math_8_ch9_mensuration",                          "display_name": "Mensuration",                             "class_level": "8", "subject": "math", "chapter_number": 9},
    "math_8_ch10": {"namespace": "math_8_ch10_exponents_and_powers",                "display_name": "Exponents and Powers",                    "class_level": "8", "subject": "math", "chapter_number": 10},
    "math_8_ch11": {"namespace": "math_8_ch11_direct_and_inverse_proportions",      "display_name": "Direct and Inverse Proportions",          "class_level": "8", "subject": "math", "chapter_number": 11},
    "math_8_ch12": {"namespace": "math_8_ch12_factorisation",                       "display_name": "Factorisation",                           "class_level": "8", "subject": "math", "chapter_number": 12},
    "math_8_ch13": {"namespace": "math_8_ch13_introduction_to_graphs",              "display_name": "Introduction to Graphs",                  "class_level": "8", "subject": "math", "chapter_number": 13},

    # CLASS 9 MATHEMATICS (Ganita Manjari)
    "math_9_ch1":  {"namespace": "math_9_ch1_coordinate_geometry",   "display_name": "Orienting Yourself: The Use of Coordinates",          "class_level": "9", "subject": "math", "chapter_number": 1},
    "math_9_ch2":  {"namespace": "math_9_ch2_linear_polynomials",    "display_name": "Introduction to Linear Polynomials",                  "class_level": "9", "subject": "math", "chapter_number": 2},
    "math_9_ch3":  {"namespace": "math_9_ch3_number_systems",        "display_name": "The World of Numbers",                               "class_level": "9", "subject": "math", "chapter_number": 3},
    "math_9_ch4":  {"namespace": "math_9_ch4_algebraic_identities",  "display_name": "Exploring Algebraic Identities",                      "class_level": "9", "subject": "math", "chapter_number": 4},
    "math_9_ch5":  {"namespace": "math_9_ch5_linear_equations",      "display_name": "Linear Equations",                                   "class_level": "9", "subject": "math", "chapter_number": 5},
    "math_9_ch6":  {"namespace": "math_9_ch6_perimeter_and_area",    "display_name": "Measuring Space: Perimeter and Area",                 "class_level": "9", "subject": "math", "chapter_number": 6},
    "math_9_ch7":  {"namespace": "math_9_ch7_probability",           "display_name": "The Mathematics of Maybe: Introduction to Probability", "class_level": "9", "subject": "math", "chapter_number": 7},
    "math_9_ch8":  {"namespace": "math_9_ch8_sequences",             "display_name": "Predicting What Comes Next: Exploring Sequences",     "class_level": "9", "subject": "math", "chapter_number": 8},

    # ─────────────────────────────────────────
    # PHYSICS (extracted from unified Science textbook)
    # ─────────────────────────────────────────
    # CLASS 7 PHYSICS
    "physics_7_ch3":  {"namespace": "physics_7_ch3_electricity_circuits",        "display_name": "Electricity: Circuits and their Components", "class_level": "7", "subject": "physics", "chapter_number": 3},
    "physics_7_ch7":  {"namespace": "physics_7_ch7_heat_transfer",               "display_name": "Heat Transfer in Nature",                    "class_level": "7", "subject": "physics", "chapter_number": 7},
    "physics_7_ch8":  {"namespace": "physics_7_ch8_measurement_time_motion",     "display_name": "Measurement of Time and Motion",             "class_level": "7", "subject": "physics", "chapter_number": 8},
    "physics_7_ch11": {"namespace": "physics_7_ch11_light_shadows_reflections",  "display_name": "Light: Shadows and Reflections",             "class_level": "7", "subject": "physics", "chapter_number": 11},

    # CLASS 8 PHYSICS
    "physics_8_ch4":  {"namespace": "physics_8_ch4_electricity_magnetic_heating", "display_name": "Electricity: Magnetic and Heating Effects", "class_level": "8", "subject": "physics", "chapter_number": 4},
    "physics_8_ch5":  {"namespace": "physics_8_ch5_exploring_forces",            "display_name": "Exploring Forces",                         "class_level": "8", "subject": "physics", "chapter_number": 5},
    "physics_8_ch6":  {"namespace": "physics_8_ch6_pressure_winds_storms",       "display_name": "Pressure, Winds, Storms, and Cyclones",     "class_level": "8", "subject": "physics", "chapter_number": 6},
    "physics_8_ch10": {"namespace": "physics_8_ch10_light_mirrors_lenses",       "display_name": "Light: Mirrors and Lenses",                 "class_level": "8", "subject": "physics", "chapter_number": 10},

    # CLASS 9 PHYSICS
    "physics_9_ch9":  {"namespace": "physics_9_ch9_motion",                    "display_name": "Motion",                            "class_level": "9", "subject": "physics", "chapter_number": 9},
    "physics_9_ch10": {"namespace": "physics_9_ch10_force_and_laws_of_motion", "display_name": "Force and Laws of Motion",          "class_level": "9", "subject": "physics", "chapter_number": 10},
    "physics_9_ch11": {"namespace": "physics_9_ch11_work_energy_machines",     "display_name": "Work, Energy and Simple Machines",  "class_level": "9", "subject": "physics", "chapter_number": 11},
    "physics_9_ch12": {"namespace": "physics_9_ch12_sound",                    "display_name": "Sound",                             "class_level": "9", "subject": "physics", "chapter_number": 12},

    # ─────────────────────────────────────────
    # CHEMISTRY (extracted from unified Science textbook)
    # ─────────────────────────────────────────
    # CLASS 7 CHEMISTRY
    "chemistry_7_ch2": {"namespace": "chemistry_7_ch2_acidic_basic_neutral",      "display_name": "Exploring Substances: Acidic, Basic, and Neutral", "class_level": "7", "subject": "chemistry", "chapter_number": 2},
    "chemistry_7_ch4": {"namespace": "chemistry_7_ch4_metals_and_nonmetals",      "display_name": "The World of Metals and Non-metals",               "class_level": "7", "subject": "chemistry", "chapter_number": 4},
    "chemistry_7_ch5": {"namespace": "chemistry_7_ch5_physical_chemical_changes", "display_name": "Changes Around Us: Physical and Chemical",         "class_level": "7", "subject": "chemistry", "chapter_number": 5},

    # CLASS 8 CHEMISTRY
    "chemistry_8_ch7": {"namespace": "chemistry_8_ch7_particulate_nature_matter",          "display_name": "Particulate Nature of Matter",                         "class_level": "8", "subject": "chemistry", "chapter_number": 7},
    "chemistry_8_ch8": {"namespace": "chemistry_8_ch8_elements_compounds_mixtures",        "display_name": "Nature of Matter: Elements, Compounds, and Mixtures",  "class_level": "8", "subject": "chemistry", "chapter_number": 8},
    "chemistry_8_ch9": {"namespace": "chemistry_8_ch9_solutes_solvents_solutions",         "display_name": "The Amazing World of Solutes, Solvents, and Solutions", "class_level": "8", "subject": "chemistry", "chapter_number": 9},

    # CLASS 9 CHEMISTRY
    "chemistry_9_ch5": {"namespace": "chemistry_9_ch5_mixtures_and_separation", "display_name": "Exploring Mixtures and Their Separation", "class_level": "9", "subject": "chemistry", "chapter_number": 5},
    "chemistry_9_ch6": {"namespace": "chemistry_9_ch6_structure_of_atom",       "display_name": "Structure of an Atom",                   "class_level": "9", "subject": "chemistry", "chapter_number": 6},
    "chemistry_9_ch7": {"namespace": "chemistry_9_ch7_atoms_and_molecules",     "display_name": "Atoms and Molecules",                    "class_level": "9", "subject": "chemistry", "chapter_number": 7},
}


# Derived helpers — keep these in sync with NAMESPACE_MAP.
ALL_CHAPTER_KEYS: list[str] = sorted(NAMESPACE_MAP.keys())
ALL_SUBJECTS: list[str] = ["math", "physics", "chemistry"]
ALL_CLASSES: list[str] = ["7", "8", "9"]


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
CLASSIFIER_PROMPT = """You are a classifier for Class 7, 8, and 9 PCM (Physics, Chemistry, Math) questions.

Given a student question, return ONLY a valid JSON object with no markdown, no preamble:
{{
  "subject": "physics" | "chemistry" | "math" | null,
  "class_level": "7" | "8" | "9" | null,
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

Student Question: {user_query}
"""


# ─────────────────────────────────────────────────────────────────────────
# ANSWER_GENERATOR_PROMPT — system prompt for the final answer
# ─────────────────────────────────────────────────────────────────────────
ANSWER_GENERATOR_PROMPT = """You are EduBot, a friendly and expert tutor for Class 7, 8, and 9 students
studying Physics, Chemistry, and Mathematics.

You are answering a Class {class_level} {subject} question about: {chapter_name}

Rules for your answer:
1. Always show step-by-step working for problems — never skip steps.
2. Use simple language appropriate for Class {class_level} students.
3. Write all mathematical expressions in LaTeX format: $formula$ for inline, $$formula$$ for block.
4. If a diagram is relevant, say "Refer to the diagram below" — diagrams will be attached separately by the system.
5. End with a one-line summary of the key concept used.
6. If the question is outside Class 7-9 PCM scope, politely say so and suggest what topic it might belong to.

Context from textbook (use this as your primary source of truth):
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
RETRIEVAL_TOP_K = 20                # initial candidates from each retriever
RERANK_TOP_K = 8                    # final chunks after rerank (when enabled)
RRF_DENSE_WEIGHT = 0.7              # alpha in RRF
RRF_SPARSE_WEIGHT = 0.3             # 1 - alpha
