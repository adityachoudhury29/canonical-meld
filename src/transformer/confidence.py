"""Confidence model.

Confidence is a function of two things:

1. **Source trust** — how reliable the source generally is (an ATS export is more
   trustworthy than a phrase scraped from free-text notes).
2. **Cross-source agreement** — independent sources asserting the same value raise
   confidence; sources disagreeing lowers it (a conflict penalty).

Everything here is pure and deterministic.
"""

from __future__ import annotations

# General reliability of each source type, in [0, 1].
SOURCE_TRUST = {
    "ats_json": 0.90,
    "recruiter_csv": 0.85,
    "linkedin": 0.80,
    "resume": 0.70,
    "github": 0.65,
    "recruiter_notes": 0.50,
    "computed": 0.40,  # values we derived ourselves
}
DEFAULT_TRUST = 0.50

# Lower number = higher priority for deterministic tie-breaks.
SOURCE_PRIORITY = {
    "ats_json": 0,
    "recruiter_csv": 1,
    "linkedin": 2,
    "resume": 3,
    "github": 4,
    "recruiter_notes": 5,
    "computed": 6,
}

_CONFLICT_PENALTY = 0.90  # applied to a winner that beat a competing value
_UNKNOWN_SKILL_FACTOR = 0.80  # skill not in the canonical taxonomy
_AGREEMENT_CAP = 0.99  # never claim absolute certainty


def trust(source: str) -> float:
    return SOURCE_TRUST.get(source, DEFAULT_TRUST)


def priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 99)


def combine_agreement(weights: list[float]) -> float:
    """Combine independent supporting weights: ``1 - ∏(1 - w)``, capped.

    One source at 0.85 → 0.85; two at 0.85 → 0.9775 (agreement raises confidence).
    """
    product = 1.0
    for w in weights:
        product *= (1.0 - max(0.0, min(1.0, w)))
    return min(_AGREEMENT_CAP, 1.0 - product)


def conflict_penalty(value_confidence: float, had_conflict: bool) -> float:
    return value_confidence * _CONFLICT_PENALTY if had_conflict else value_confidence


def skill_factor(recognized: bool) -> float:
    return 1.0 if recognized else _UNKNOWN_SKILL_FACTOR


def rounded(value: float) -> float:
    return round(value, 2)
