"""Resume — an unstructured source (``.txt`` prose, or ``.pdf`` if ``pypdf`` is installed).

Resume layouts are wildly inconsistent, so this is a *best-effort* section parser:
it pulls contacts/links from anywhere, then parses Skills / Experience / Education
sections when it can recognize them. Anything it cannot confidently parse is left
out rather than guessed, and a weird layout degrades to "just the contacts".
"""

from __future__ import annotations

import os
import re

from ..models import SourceRecord
from ..normalize import text as T
from .base import SourceError, parse_location, read_text_file

SOURCE_ID = "resume"

# section header -> canonical section key
_SECTION_HEADERS = [
    (re.compile(r"^\s*(technical skills|core competencies|skills|technologies|tech stack)\s*:?\s*$", re.I), "skills"),
    (re.compile(r"^\s*(work experience|professional experience|experience|employment( history)?)\s*:?\s*$", re.I), "experience"),
    (re.compile(r"^\s*(education|academics?|academic background)\s*:?\s*$", re.I), "education"),
    (re.compile(r"^\s*(summary|profile|objective|about)\s*:?\s*$", re.I), "summary"),
]

_DATE_RANGE = re.compile(
    r"([A-Za-z]{3,9}\.?\s+\d{4}|\d{1,2}[/-]\d{4}|\d{4})\s*(?:-|–|—|to)\s*"
    r"([A-Za-z]{3,9}\.?\s+\d{4}|\d{1,2}[/-]\d{4}|\d{4}|present|current|now|ongoing)",
    re.I,
)
_YEAR = re.compile(r"(19|20)\d{2}")


def parse(spec: dict, warnings: list[str]) -> list[SourceRecord]:
    text = _read(spec["path"], warnings)
    if not text or not text.strip():
        warnings.append(f"{SOURCE_ID}: no extractable text in {spec['path']}")
        return []

    rec = SourceRecord(source=SOURCE_ID, record_id=f"resume:{os.path.basename(spec['path'])}")
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Contacts and links can appear anywhere.
    for email in T.extract_emails(text):
        rec.add("emails", email, "regex:email")
    for phone in T.extract_phones(text):
        rec.add("phones", phone, "regex:phone")
    if (li := T.linkedin_username(text)):
        rec.add("links.linkedin", f"https://linkedin.com/in/{li}", "regex:linkedin")
    if (gh := T.github_username(text)):
        rec.add("links.github", f"https://github.com/{gh}", "regex:github")

    _parse_header(rec, lines)
    _parse_location(rec, lines)
    sections = _split_sections(lines)
    _parse_skills(rec, sections.get("skills", []))
    _parse_experience(rec, sections.get("experience", []))
    _parse_education(rec, sections.get("education", []))
    return [rec] if rec.claims else []


def _read(path: str, warnings: list[str]) -> str:
    if path.lower().endswith(".pdf"):
        try:
            import pypdf  # optional dependency
        except ImportError:
            warnings.append(f"{SOURCE_ID}: pypdf not installed; cannot read {path}")
            return ""
        try:
            reader = pypdf.PdfReader(path)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise SourceError(f"{SOURCE_ID}: cannot read PDF {path}: {exc}") from exc
    return read_text_file(path)


def _is_header(line: str) -> str | None:
    for pattern, key in _SECTION_HEADERS:
        if pattern.match(line):
            return key
    return None


def _name_like(line: str) -> bool:
    words = line.split()
    if not (1 <= len(words) <= 4):
        return False
    if "@" in line or any(ch.isdigit() for ch in line):
        return False
    return all(w[:1].isupper() for w in words if w[:1].isalpha())


def _parse_header(rec: SourceRecord, lines: list[str]) -> None:
    """First name-like line is the name; the line after it (if any) is the headline."""
    non_empty = [ln.strip() for ln in lines if ln.strip()]
    for i, line in enumerate(non_empty[:5]):
        if _is_header(line) or "@" in line:
            continue
        if _name_like(line):
            rec.add("full_name", line, "resume_header:name")
            if i + 1 < len(non_empty):
                nxt = non_empty[i + 1]
                if not _is_header(nxt) and "@" not in nxt and len(nxt) <= 80:
                    rec.add("headline", nxt, "resume_header:headline")
            return


def _parse_location(rec: SourceRecord, lines: list[str]) -> None:
    """Look for a 'City, Country' line in the resume header block."""
    non_empty = [ln.strip() for ln in lines if ln.strip()]
    for line in non_empty[:8]:
        if "@" in line or "http" in line.lower() or _is_header(line) or "," not in line:
            continue
        loc = parse_location(line)
        if loc["country"]:
            rec.add("location.city", loc["city"], "resume_header:location")
            rec.add("location.region", loc["region"], "resume_header:location")
            rec.add("location.country", loc["country"], "resume_header:location")
            return


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines:
        key = _is_header(line.strip())
        if key:
            current = key
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return sections


def _parse_skills(rec: SourceRecord, body: list[str]) -> None:
    for line in body:
        line = re.sub(r"^[\s•\-*]+", "", line).strip()
        # drop a leading "Languages:" style label
        line = re.sub(r"^[A-Za-z ]{1,20}:", "", line).strip()
        for token in re.split(r"[,;|]", line):
            rec.add("skills", token.strip(), "resume_section:skills")


def _split_blocks(body: list[str]) -> list[list[str]]:
    blocks, cur = [], []
    for line in body:
        if line.strip():
            cur.append(line.strip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def _parse_experience(rec: SourceRecord, body: list[str]) -> None:
    for block in _split_blocks(body):
        text = " ".join(block)
        start = end = None
        if (m := _DATE_RANGE.search(text)):
            start, end = m.group(1), m.group(2)
        title, company = _split_title_company(block[0])
        summary = " ".join(block[1:]).strip() or None
        if any([company, title, start]):
            rec.add("experience", {
                "company": company, "title": title,
                "start": start, "end": end, "summary": summary,
            }, "resume_section:experience")


def _split_title_company(line: str) -> tuple[str | None, str | None]:
    line = _DATE_RANGE.sub("", line).strip(" \t-–—|,()")
    if " at " in line.lower():
        idx = line.lower().index(" at ")
        return line[:idx].strip() or None, line[idx + 4:].strip() or None
    for sep in ("—", "–", "|", " - ", ","):
        if sep in line:
            left, right = line.split(sep, 1)
            return left.strip() or None, right.strip() or None
    return (line.strip() or None), None


def _parse_education(rec: SourceRecord, body: list[str]) -> None:
    for block in _split_blocks(body):
        text = " ".join(block)
        year = None
        if (m := _YEAR.search(text)):
            year = m.group(0)
        institution = degree = field_ = None
        parts = [p.strip() for p in re.split(r"[,–—|]", _YEAR.sub("", block[0])) if p.strip()]
        if parts:
            institution = parts[0]
        if len(parts) >= 2:
            degree = parts[1]
        if len(parts) >= 3:
            field_ = parts[2]
        if institution or degree:
            rec.add("education", {
                "institution": institution, "degree": degree,
                "field": field_, "end_year": year,
            }, "resume_section:education")
