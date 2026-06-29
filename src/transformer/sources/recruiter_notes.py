"""Recruiter notes (.txt) — the messiest unstructured source: free-form prose.

We extract only what we can pull out with high-precision patterns (contacts,
explicit "N years", named skills, "at <Company> as <Title>"). This is the
lowest-trust source, so the merge step weights it accordingly. Nothing is
inferred beyond what the text plainly states.
"""

from __future__ import annotations

import os
import re

from ..models import SourceRecord
from ..normalize import skills as skills_norm
from ..normalize import text as T
from .base import read_text_file

SOURCE_ID = "recruiter_notes"

_NAME = re.compile(r"(?:candidate|name|re)\s*:\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})")
_YEARS = re.compile(r"(\d{1,2})(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)\b", re.I)
_AT_AS = re.compile(r"\bat\s+([A-Z][\w&.\- ]{1,40}?)\s+as\s+(?:an?\s+)?([A-Za-z][\w/\- ]{2,40})", re.I)


def parse(spec: dict, warnings: list[str]) -> list[SourceRecord]:
    text = read_text_file(spec["path"])
    if not text.strip():
        warnings.append(f"{SOURCE_ID}: empty file {spec['path']}")
        return []

    rec = SourceRecord(source=SOURCE_ID, record_id=f"notes:{os.path.basename(spec['path'])}")
    # Collapse newlines/runs of whitespace so prose that wraps across lines (e.g.
    # a title split as "Senior Backend\nEngineer") still matches cleanly.
    flat = re.sub(r"\s+", " ", text)

    if (m := _NAME.search(flat)):
        rec.add("full_name", m.group(1).strip(), "regex:name_label")
    for email in T.extract_emails(text):
        rec.add("emails", email, "regex:email")
    for phone in T.extract_phones(text):
        rec.add("phones", phone, "regex:phone")
    if (li := T.linkedin_username(text)):
        rec.add("links.linkedin", f"https://linkedin.com/in/{li}", "regex:linkedin")
    if (gh := T.github_username(text)):
        rec.add("links.github", f"https://github.com/{gh}", "regex:github")

    if (m := _YEARS.search(flat)):
        rec.add("years_experience", m.group(1), "regex:years_experience")

    if (m := _AT_AS.search(flat)):
        rec.add("experience", {
            "company": m.group(1).strip(), "title": m.group(2).strip(),
            "start": None, "end": None, "summary": None,
        }, "regex:at_company_as_title")

    for skill in _scan_known_skills(text):
        rec.add("skills", skill, "keyword_scan:skill")

    return [rec] if rec.claims else []


def _scan_known_skills(text: str) -> list[str]:
    """Find mentions of recognized skills using word-boundary matching."""
    low = text.lower()
    found, seen = [], set()
    # longest aliases first so "google cloud" wins over "go"
    for alias in sorted(skills_norm._ALIASES, key=len, reverse=True):
        pattern = r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#.])"
        if re.search(pattern, low):
            canonical = skills_norm._ALIASES[alias]
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
    return found
