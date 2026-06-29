"""ATS JSON blob — a structured source whose field names do NOT match ours.

This is the "remapping" workhorse: the ATS uses its own vocabulary
(``emailAddress``, ``currentEmployer``, ``workHistory`` ...) and we translate it
onto canonical fields. Key matching is case- and separator-insensitive
(``country_code`` == ``countryCode`` == ``CountryCode``), so we tolerate the
schema drift different ATS vendors ship.

Accepts a top-level object, a ``{"candidates": [...]}`` envelope, or a bare list.
"""

from __future__ import annotations

import json

from ..models import SourceRecord
from .base import SourceError, parse_location, read_text_file

SOURCE_ID = "ats_json"


def _norm_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _pick(obj: dict, *aliases: str):
    """First non-empty value among the given (separator-insensitive) keys."""
    index = {_norm_key(k): v for k, v in obj.items()}
    for alias in aliases:
        val = index.get(_norm_key(alias))
        if val not in (None, "", [], {}):
            return val
    return None


def parse(spec: dict, warnings: list[str]) -> list[SourceRecord]:
    text = read_text_file(spec["path"])
    if not text.strip():
        warnings.append(f"{SOURCE_ID}: empty file {spec['path']}")
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"{SOURCE_ID}: invalid JSON in {spec['path']}: {exc}") from exc

    candidates = _as_candidate_list(data)
    records: list[SourceRecord] = []
    for i, cand in enumerate(candidates, start=1):
        if not isinstance(cand, dict):
            warnings.append(f"{SOURCE_ID}: skipped non-object candidate #{i}")
            continue
        try:
            rec = _parse_candidate(spec["path"], i, cand)
        except Exception as exc:
            warnings.append(f"{SOURCE_ID}: skipped candidate #{i}: {exc}")
            continue
        if rec.claims:
            records.append(rec)
    return records


def _as_candidate_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("candidates", "results", "data", "records", "applicants"):
            val = _pick(data, key)
            if isinstance(val, list):
                return val
        return [data]  # a single candidate object
    return []


def _parse_candidate(path: str, idx: int, c: dict) -> SourceRecord:
    rec = SourceRecord(source=SOURCE_ID, record_id=f"{path}#cand{idx}")

    # name: explicit full name, else first + last
    name = _pick(c, "fullName", "name", "candidateName", "displayName")
    if not name:
        first = _pick(c, "firstName", "givenName") or ""
        last = _pick(c, "lastName", "familyName", "surname") or ""
        name = (f"{first} {last}").strip()
    rec.add("full_name", name, "ats_field:name")

    emails = _pick(c, "emails", "emailAddresses", "emailAddress", "email", "primaryEmail")
    for email in _as_str_list(emails):
        rec.add("emails", email, "ats_field:email")

    phones = _pick(c, "phones", "phoneNumbers", "phoneNumber", "phone", "mobile")
    for phone in _as_str_list(phones):
        rec.add("phones", phone, "ats_field:phone")

    rec.add("headline", _pick(c, "headline", "summary", "about", "title", "objective"),
            "ats_field:headline")

    years = _pick(c, "yearsOfExperience", "yearsExperience", "totalExperience",
                  "experienceYears")
    rec.add("years_experience", years, "ats_field:years_experience")

    # location: structured fields first, else a single location string
    city = _pick(c, "city", "locationCity")
    region = _pick(c, "state", "region", "province", "locationState")
    country = _pick(c, "country", "countryCode", "locationCountry")
    if not (city or region or country):
        loc = parse_location(_pick(c, "location", "address") or "")
        city, region, country = loc["city"], loc["region"], loc["country"]
    rec.add("location.city", city, "ats_field:location")
    rec.add("location.region", region, "ats_field:location")
    rec.add("location.country", country, "ats_field:location")

    rec.add("links.linkedin", _pick(c, "linkedinUrl", "linkedin", "linkedInProfile"),
            "ats_field:linkedin")
    rec.add("links.github", _pick(c, "githubUrl", "github"), "ats_field:github")
    rec.add("links.portfolio", _pick(c, "website", "portfolio", "personalSite", "blog"),
            "ats_field:portfolio")

    for skill in _as_skill_list(_pick(c, "skills", "skillSet", "competencies", "tags")):
        rec.add("skills", skill, "ats_field:skills")

    for item in _as_list(_pick(c, "workHistory", "experience", "employment",
                               "positions", "workExperience")):
        if isinstance(item, dict):
            rec.add("experience", {
                "company": _pick(item, "employer", "company", "organization", "companyName"),
                "title": _pick(item, "position", "title", "role", "jobTitle"),
                "start": _to_str(_pick(item, "startDate", "start", "from", "startYear")),
                "end": _to_str(_pick(item, "endDate", "end", "to", "endYear")),
                "summary": _pick(item, "description", "summary", "responsibilities"),
            }, "ats_field:work_history")

    for item in _as_list(_pick(c, "education", "educationHistory", "schools", "academics")):
        if isinstance(item, dict):
            rec.add("education", {
                "institution": _pick(item, "school", "institution", "university", "college"),
                "degree": _pick(item, "degree", "qualification"),
                "field": _pick(item, "fieldOfStudy", "field", "major", "discipline"),
                "end_year": _to_str(_pick(item, "graduationYear", "gradYear", "endYear",
                                          "endDate", "year")),
            }, "ats_field:education")

    return rec


def _to_str(value):
    return None if value is None else str(value)


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_str_list(value) -> list[str]:
    out = []
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            val = _pick(item, "value", "address", "email", "number", "phone")
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
    return out


def _as_skill_list(value) -> list[str]:
    out = []
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            name = _pick(item, "name", "skill", "value", "label")
            if isinstance(name, str) and name.strip():
                out.append(name.strip())
    return out
