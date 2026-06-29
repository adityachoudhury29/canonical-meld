"""Date normalization to ``YYYY-MM`` (the spec's format for experience dates).

Accepts the messy variety real resumes/ATS exports contain. When only a year is
known we keep ``YYYY`` rather than inventing a month. "present"/"current" is a
distinct concept (an open-ended range), surfaced via :func:`is_present`.
"""

from __future__ import annotations

import re
from typing import Optional

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_PRESENT = {"present", "current", "now", "ongoing", "till date", "to date"}


def is_present(raw: str) -> bool:
    return bool(raw) and raw.strip().lower() in _PRESENT


def _fmt(year: int, month: Optional[int]) -> Optional[str]:
    if not (1900 <= year <= 2100):
        return None
    if month is None:
        return f"{year:04d}"
    if not (1 <= month <= 12):
        return f"{year:04d}"
    return f"{year:04d}-{month:02d}"


def to_year_month(raw: str) -> Optional[str]:
    """Parse a single date token to ``YYYY-MM`` (or ``YYYY`` if month unknown).

    Returns ``None`` for "present" tokens and anything unparseable.
    """
    if not raw or not raw.strip():
        return None
    s = raw.strip().lower()
    if s in _PRESENT:
        return None

    # 2020-01 / 2020/1 / 2020.01
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})", s)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)))

    # 01/2020 / 1-2020
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", s)
    if m:
        return _fmt(int(m.group(2)), int(m.group(1)))

    # "Jan 2020" / "January, 2020"
    m = re.fullmatch(r"([a-z]+)\.?,?\s+(\d{4})", s)
    if m and m.group(1) in _MONTHS:
        return _fmt(int(m.group(2)), _MONTHS[m.group(1)])

    # "2020 Jan"
    m = re.fullmatch(r"(\d{4})\s+([a-z]+)\.?", s)
    if m and m.group(2) in _MONTHS:
        return _fmt(int(m.group(1)), _MONTHS[m.group(2)])

    # Bare year
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return _fmt(int(m.group(1)), None)

    return None


def to_year(raw: str) -> Optional[int]:
    """Extract a 4-digit graduation/end year, or ``None``."""
    ym = to_year_month(raw)
    if ym:
        return int(ym[:4])
    m = re.search(r"(19|20)\d{2}", raw or "")
    return int(m.group(0)) if m else None
