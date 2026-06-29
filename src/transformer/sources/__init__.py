"""Source adapter registry + type detection.

The pipeline calls :func:`load_source` per declared source. Each call is isolated:
a hard failure raises :class:`SourceError`, which the pipeline catches and records
as a warning so a single bad source never crashes the run.
"""

from __future__ import annotations

import json
import os

from ..models import SourceRecord
from . import ats_json, github, recruiter_csv, recruiter_notes, resume_text
from .base import SourceError

REGISTRY = {
    mod.SOURCE_ID: mod.parse
    for mod in (recruiter_csv, ats_json, github, resume_text, recruiter_notes)
}


def load_source(spec: dict, warnings: list[str]) -> list[SourceRecord]:
    stype = spec.get("type") or detect(spec)
    if stype not in REGISTRY:
        raise SourceError(f"unknown source type: {stype!r}")
    return REGISTRY[stype](spec, warnings)


def detect(spec: dict) -> str:
    """Infer the source type from a URL or file extension/content."""
    if "github.com" in (spec.get("url") or ""):
        return "github"
    path = spec.get("path") or spec.get("fixture") or ""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return "recruiter_csv"
    if ext in (".pdf", ".docx"):
        return "resume"
    if ext == ".json":
        return _detect_json(path)
    if ext == ".txt":
        base = os.path.basename(path).lower()
        if "note" in base:
            return "recruiter_notes"
        if "resume" in base or "cv" in base:
            return "resume"
        return _detect_text(path)
    raise SourceError(f"cannot detect source type for {path!r}")


def _detect_json(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return "ats_json"  # let the adapter surface the real error
    keys = set()
    if isinstance(data, dict):
        keys = {k.lower() for k in data}
    if keys & {"login", "public_repos", "repos", "user"}:
        return "github"
    return "ats_json"


def _detect_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(2000).lower()
    except OSError:
        return "recruiter_notes"
    if any(h in head for h in ("experience", "education", "skills", "summary")):
        return "resume"
    return "recruiter_notes"
