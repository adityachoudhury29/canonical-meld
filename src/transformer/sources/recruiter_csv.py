"""Recruiter CSV export — a structured source.

Columns per the spec: ``name, email, phone, current_company, title`` (header
matching is case-insensitive and tolerant of common aliases). One row → one
:class:`SourceRecord`. A malformed row is skipped, never guessed.
"""

from __future__ import annotations

import csv
import io

from ..models import SourceRecord
from .base import SourceError, parse_location, read_text_file, split_multi

SOURCE_ID = "recruiter_csv"

# normalized header (lower, stripped) -> canonical column role
_HEADER_ALIASES = {
    "name": "name", "full name": "name", "full_name": "name",
    "candidate": "name", "candidate name": "name",
    "email": "email", "email address": "email", "e-mail": "email", "emails": "email",
    "phone": "phone", "phone number": "phone", "mobile": "phone",
    "telephone": "phone", "cell": "phone", "phones": "phone",
    "current_company": "company", "current company": "company",
    "company": "company", "employer": "company",
    "title": "title", "job title": "title", "role": "title", "position": "title",
    "location": "location", "city": "location",
}


def parse(spec: dict, warnings: list[str]) -> list[SourceRecord]:
    text = read_text_file(spec["path"])
    if not text.strip():
        warnings.append(f"{SOURCE_ID}: empty file {spec['path']}")
        return []

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        warnings.append(f"{SOURCE_ID}: no header row in {spec['path']}")
        return []

    # Map each physical column to its canonical role.
    colmap: dict[str, str] = {}
    for col in reader.fieldnames:
        role = _HEADER_ALIASES.get((col or "").strip().lower())
        if role:
            colmap[col] = role

    records: list[SourceRecord] = []
    for i, row in enumerate(reader, start=1):
        try:
            rec = _parse_row(spec["path"], i, row, colmap)
        except Exception as exc:  # one bad row must not sink the file
            warnings.append(f"{SOURCE_ID}: skipped row {i} in {spec['path']}: {exc}")
            continue
        if rec and rec.claims:
            records.append(rec)
    return records


def _get(row: dict, colmap: dict, role: str) -> str:
    for col, mapped in colmap.items():
        if mapped == role:
            val = row.get(col)
            if val and val.strip():
                return val.strip()
    return ""


def _parse_row(path: str, idx: int, row: dict, colmap: dict) -> SourceRecord:
    rec = SourceRecord(source=SOURCE_ID, record_id=f"{path}#row{idx}")
    rec.add("full_name", _get(row, colmap, "name"), "csv_column:name")
    for email in split_multi(_get(row, colmap, "email")):
        rec.add("emails", email, "csv_column:email")
    for phone in split_multi(_get(row, colmap, "phone")):
        rec.add("phones", phone, "csv_column:phone")

    company = _get(row, colmap, "company")
    title = _get(row, colmap, "title")
    if company or title:
        rec.add(
            "experience",
            {"company": company or None, "title": title or None,
             "start": None, "end": None, "summary": None},
            "csv_column:current_company+title",
        )

    loc = parse_location(_get(row, colmap, "location"))
    rec.add("location.city", loc["city"], "csv_column:location")
    rec.add("location.region", loc["region"], "csv_column:location")
    rec.add("location.country", loc["country"], "csv_column:location")
    return rec
