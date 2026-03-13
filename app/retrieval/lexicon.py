"""
SDG retrieval lexicon.

Defines:
    SDG_KEYWORDS     — per-SDG keyword lists for scoring keyword overlap
    SDG_QUERY_TEXT   — a combined query string for semantic retrieval
    BOILERPLATE_PATTERNS — regex patterns that identify generic sustainability
                           rhetoric with no supporting evidence

This module is intentionally code-only (no LLM involvement).
"""

from __future__ import annotations

import re
from typing import Dict, List, Pattern

# ---------------------------------------------------------------------------
# Per-SDG keyword sets
# ---------------------------------------------------------------------------

SDG_KEYWORDS: Dict[str, List[str]] = {
    "SDG 1": [
        "poverty", "extreme poverty", "social protection", "economic inclusion",
        "livelihoods", "income", "financial access", "microfinance",
    ],
    "SDG 2": [
        "hunger", "food security", "nutrition", "sustainable agriculture",
        "farmers", "smallholder", "food systems", "crop yield", "food waste",
        "agroforestry",
    ],
    "SDG 3": [
        "health", "safety", "wellbeing", "occupational health", "injury rate",
        "fatality", "mental health", "healthcare access", "disease prevention",
        "tafr", "ltifr",
    ],
    "SDG 4": [
        "education", "training", "skills development", "literacy",
        "vocational", "learning", "school", "scholarship", "apprenticeship",
    ],
    "SDG 5": [
        "gender equality", "women", "female representation", "gender pay gap",
        "diversity", "inclusion", "women empowerment", "equal opportunity",
        "gender-based violence",
    ],
    "SDG 6": [
        "water", "clean water", "water stewardship", "water withdrawal",
        "water recycling", "wastewater", "sanitation", "water intensity",
        "water risk",
    ],
    "SDG 7": [
        "energy", "renewable energy", "solar", "wind", "clean energy",
        "energy efficiency", "energy intensity", "electricity", "fossil fuel",
        "energy transition",
    ],
    "SDG 8": [
        "decent work", "fair wage", "living wage", "labour rights",
        "employment", "economic growth", "modern slavery", "forced labour",
        "child labour", "worker rights",
    ],
    "SDG 9": [
        "innovation", "infrastructure", "industry", "research and development",
        "r&d", "digitisation", "technology", "manufacturing",
    ],
    "SDG 10": [
        "inequality", "equal opportunity", "pay equity", "social inclusion",
        "marginalized", "indigenous", "disability",
    ],
    "SDG 11": [
        "communities", "sustainable cities", "urban", "affordable housing",
        "community investment", "local procurement",
    ],
    "SDG 12": [
        "responsible consumption", "responsible production", "circular economy",
        "waste reduction", "recycling", "packaging", "sustainable sourcing",
        "supply chain", "product stewardship",
    ],
    "SDG 13": [
        "climate", "climate change", "emissions", "ghg", "greenhouse gas",
        "carbon", "net zero", "decarbonisation", "scope 1", "scope 2",
        "scope 3", "paris agreement", "carbon neutral", "climate risk",
        "tcfd", "transition plan",
    ],
    "SDG 14": [
        "ocean", "marine", "water pollution", "plastic pollution",
        "aquatic ecosystem", "fisheries", "biodiversity ocean",
    ],
    "SDG 15": [
        "biodiversity", "land use", "deforestation", "forest",
        "ecosystem", "habitat", "species", "conservation", "tnfd",
        "nature-based solutions",
    ],
    "SDG 16": [
        "governance", "anti-corruption", "transparency", "accountability",
        "rule of law", "human rights", "ethics", "board oversight",
        "whistleblowing", "compliance",
    ],
    "SDG 17": [
        "partnerships", "multi-stakeholder", "public-private partnership",
        "collaboration", "sustainable development goals", "sdg",
        "reporting framework", "gri", "sasb",
    ],
}

# ---------------------------------------------------------------------------
# Combined query for semantic retrieval
# (used as the embedding query to find SDG-relevant chunks)
# ---------------------------------------------------------------------------

SDG_QUERY_TEXT: str = (
    "sustainable development goals SDG climate emissions water waste energy "
    "governance health safety education communities farmers livelihoods "
    "diversity human rights biodiversity supply chain renewable carbon "
    "equality inclusion economic growth responsible consumption innovation "
    "partnership anti-corruption transparency measurable target KPI initiative "
    "policy board oversight scope 1 scope 2 net zero circular economy"
)

# ---------------------------------------------------------------------------
# Boilerplate detection
# ---------------------------------------------------------------------------

# Patterns that strongly suggest generic, unsupported sustainability rhetoric.
# A chunk matching these patterns with NO action/metric/oversight language
# will have its retrieval score penalised.
_BOILERPLATE_RAW: List[str] = [
    r"\bwe are committed to sustainability\b",
    r"\bour commitment to sustainable development\b",
    r"\bsustainability is (at the )?core\b",
    r"\bwe believe in a sustainable future\b",
    r"\bwe strive to\b",
    r"\bwe aspire to\b",
    r"\bwe recognise the importance of\b",
    r"\bwe acknowledge (our|the)\b",
    r"\bgoing forward[,.]?\s*we\b",
    r"\bwe remain committed\b",
    r"\bour vision is to\b",
]

BOILERPLATE_PATTERNS: List[Pattern] = [
    re.compile(p, re.IGNORECASE) for p in _BOILERPLATE_RAW
]

# Action/evidence signals — if any of these are present, the boilerplate
# penalty is NOT applied even if boilerplate text is also present.
_ACTION_SIGNALS_RAW: List[str] = [
    r"\b\d+[\.,]?\d*\s*%",                    # percentages
    r"\b\d{4}\b",                              # years (e.g. targets)
    r"\btonne[s]?\b", r"\bmt\b",              # mass metrics
    r"\bgwh\b", r"\bmwh\b", r"\bkwh\b",       # energy
    r"\bm[3³]\b",                              # volume (water)
    r"\btarget[s]?\b",
    r"\bkpi\b",
    r"\breduced by\b",
    r"\bincreased by\b",
    r"\bby \d{4}\b",
    r"\bcommittee\b",
    r"\bboard\b",
    r"\bexecutive\b",
    r"\baudited\b",
    r"\bverified\b",
    r"\binitiative[s]?\b",
    r"\bpolic(y|ies)\b",
]

ACTION_SIGNAL_PATTERNS: List[Pattern] = [
    re.compile(p, re.IGNORECASE) for p in _ACTION_SIGNALS_RAW
]


def is_boilerplate(text: str) -> bool:
    """
    Return True if the text looks like generic sustainability boilerplate
    with no supporting action, metric, or governance signal.
    """
    has_boilerplate = any(p.search(text) for p in BOILERPLATE_PATTERNS)
    if not has_boilerplate:
        return False
    has_action = any(p.search(text) for p in ACTION_SIGNAL_PATTERNS)
    return not has_action


def get_keyword_hits(text: str) -> List[str]:
    """
    Return a de-duplicated list of SDG keywords found in the given text.

    Args:
        text: Chunk text to scan.

    Returns:
        List of matched keywords (lowercased, de-duplicated).
    """
    text_lower = text.lower()
    hits: List[str] = []
    seen = set()
    for sdg, keywords in SDG_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower and kw not in seen:
                hits.append(kw)
                seen.add(kw)
    return hits
