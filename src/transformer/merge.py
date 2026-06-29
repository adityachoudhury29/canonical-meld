"""Entity resolution + per-field merge + confidence + provenance.

This turns a flat list of :class:`SourceRecord` (raw claims from every source)
into one :class:`CanonicalProfile` per real person:

1. **resolve_entities** — cluster records that refer to the same person using
   strong identity anchors (email / phone / linkedin / github). Name alone never
   merges, to avoid false "two John Smiths" joins.
2. **normalize** — apply the normalizers to every claim, using cross-source
   context (the cluster's resolved country becomes the phone region hint).
3. **merge** — per field: scalars pick a *winner*; multi-value fields union+dedupe.
4. **score** — attach confidence and a provenance trail to everything emitted.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from . import confidence as C
from .models import (
    CanonicalProfile,
    Education,
    Experience,
    Links,
    Location,
    ProvenanceEntry,
    Skill,
    SourceRecord,
)
from .normalize import country as country_norm
from .normalize import dates as date_norm
from .normalize import phone as phone_norm
from .normalize import skills as skills_norm
from .normalize import text as text_norm

# Canonical ordering used for stable provenance output.
FIELD_ORDER = [
    "full_name", "emails", "phones",
    "location.city", "location.region", "location.country",
    "links.linkedin", "links.github", "links.portfolio", "links.other",
    "headline", "years_experience", "skills", "experience", "education",
]
_FIELD_INDEX = {f: i for i, f in enumerate(FIELD_ORDER)}


# ---------------------------------------------------------------------------
# 1. Entity resolution
# ---------------------------------------------------------------------------

def resolve_entities(records: list[SourceRecord]) -> list[list[SourceRecord]]:
    """Cluster records by shared identity anchors (union-find)."""
    parent = list(range(len(records)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    owner: dict[str, int] = {}
    for i, rec in enumerate(records):
        for anchor in _anchors(rec):
            if anchor in owner:
                union(i, owner[anchor])
            else:
                owner[anchor] = i

    groups: dict[int, list[SourceRecord]] = defaultdict(list)
    for i, rec in enumerate(records):
        groups[find(i)].append(rec)
    # Deterministic order: by smallest original index in each cluster.
    return [groups[k] for k in sorted(groups)]


def _anchors(rec: SourceRecord) -> set[str]:
    anchors: set[str] = set()
    for claim in rec.claims:
        if claim.field == "emails":
            anchors.add("email:" + text_norm.normalize_email(claim.value))
        elif claim.field == "phones":
            digits = re.sub(r"\D", "", str(claim.value))
            if len(digits) >= 10:
                anchors.add("phone:" + digits[-10:])
        elif claim.field == "links.linkedin":
            if (u := text_norm.linkedin_username(claim.value)):
                anchors.add("li:" + u.lower())
        elif claim.field == "links.github":
            if (u := text_norm.github_username(claim.value)):
                anchors.add("gh:" + u.lower())
    return anchors


# ---------------------------------------------------------------------------
# 2. Normalize claims (with cluster context)
# ---------------------------------------------------------------------------

def _region_hint(records: list[SourceRecord]) -> str | None:
    """Most-trusted resolved country in the cluster → phone parsing region."""
    best, best_trust = None, -1.0
    for rec in records:
        for claim in rec.claims:
            if claim.field == "location.country":
                iso = country_norm.to_iso_alpha2(str(claim.value))
                if iso and C.trust(rec.source) > best_trust:
                    best, best_trust = iso, C.trust(rec.source)
    return best


def _normalized_entries(records: list[SourceRecord], region: str | None) -> dict[str, list[dict]]:
    """Group normalized claims by field. Drops anything that fails to normalize."""
    out: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        for claim in rec.claims:
            value, extra = _normalize(claim.field, claim.value, region)
            if value is None:
                continue
            entry = {"value": value, "source": rec.source, "method": claim.method}
            entry.update(extra)
            out[claim.field].append(entry)
    return out


def _normalize(field: str, raw: Any, region: str | None) -> tuple[Any, dict]:
    """Return ``(normalized_value, extra)``; ``value=None`` means drop the claim."""
    if field == "emails":
        return text_norm.normalize_email(raw) or None, {}
    if field == "phones":
        return phone_norm.to_e164(str(raw), region), {}
    if field == "location.country":
        return country_norm.to_iso_alpha2(str(raw)), {}
    if field in ("location.city", "location.region", "full_name", "headline"):
        return text_norm.clean(str(raw)) or None, {}
    if field in ("links.linkedin", "links.github", "links.portfolio", "links.other"):
        return text_norm.normalize_url(str(raw)) or None, {}
    if field == "years_experience":
        return _to_number(raw), {}
    if field == "skills":
        result = skills_norm.canonicalize(str(raw))
        if result is None:
            return None, {}
        name, recognized = result
        return name, {"recognized": recognized}
    if field == "experience":
        return _normalize_experience(raw), {}
    if field == "education":
        return _normalize_education(raw), {}
    return None, {}


def _to_number(raw: Any):
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return _tidy_number(float(raw))
    m = re.search(r"\d+(?:\.\d+)?", str(raw))
    return _tidy_number(float(m.group())) if m else None


def _tidy_number(value: float):
    return int(value) if value.is_integer() else round(value, 1)


def _normalize_experience(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    end_raw = raw.get("end")
    end = None if (end_raw and date_norm.is_present(str(end_raw))) else (
        date_norm.to_year_month(str(end_raw)) if end_raw else None
    )
    norm = {
        "company": text_norm.clean(str(raw.get("company"))) if raw.get("company") else None,
        "title": text_norm.clean(str(raw.get("title"))) if raw.get("title") else None,
        "start": date_norm.to_year_month(str(raw["start"])) if raw.get("start") else None,
        "end": end,
        "summary": text_norm.clean(str(raw.get("summary"))) if raw.get("summary") else None,
    }
    return norm if any(norm.values()) else None


def _normalize_education(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    norm = {
        "institution": text_norm.clean(str(raw.get("institution"))) if raw.get("institution") else None,
        "degree": text_norm.clean(str(raw.get("degree"))) if raw.get("degree") else None,
        "field": text_norm.clean(str(raw.get("field"))) if raw.get("field") else None,
        "end_year": date_norm.to_year(str(raw["end_year"])) if raw.get("end_year") else None,
    }
    return norm if any(v is not None for v in norm.values()) else None


# ---------------------------------------------------------------------------
# 3 + 4. Merge a cluster into one canonical profile
# ---------------------------------------------------------------------------

def merge_cluster(records: list[SourceRecord]) -> CanonicalProfile:
    region = _region_hint(records)
    entries = _normalized_entries(records, region)
    provenance: list[ProvenanceEntry] = []
    field_conf: dict[str, float] = {}

    def scalar(field: str):
        value, conf, prov = _resolve_scalar(field, entries.get(field, []))
        if value is not None:
            field_conf[field] = conf
            provenance.extend(prov)
        return value

    def multi(field: str):
        values, conf, prov = _resolve_multi(field, entries.get(field, []))
        if values:
            field_conf[field] = conf
            provenance.extend(prov)
        return values

    full_name = scalar("full_name")
    headline = scalar("headline")
    years = scalar("years_experience")
    location = Location(
        city=scalar("location.city"),
        region=scalar("location.region"),
        country=scalar("location.country"),
    )
    links = Links(
        linkedin=scalar("links.linkedin"),
        github=scalar("links.github"),
        portfolio=scalar("links.portfolio"),
        other=multi("links.other"),
    )
    emails = multi("emails")
    phones = multi("phones")
    skills = _resolve_skills(entries.get("skills", []), provenance, field_conf)
    experience = _resolve_objects(
        "experience", entries.get("experience", []), provenance, field_conf,
        key=lambda d: (_lc(d.get("company")), _lc(d.get("title"))),
        builder=_build_experience, order=_experience_sort_key,
    )
    education = _resolve_objects(
        "education", entries.get("education", []), provenance, field_conf,
        key=lambda d: (_lc(d.get("institution")), _lc(d.get("degree"))),
        builder=_build_education, order=lambda e: (-(e.end_year or 0), e.institution or ""),
    )

    if years is None:
        derived = _derive_years(experience)
        if derived is not None:
            years = derived
            field_conf["years_experience"] = C.rounded(C.trust("computed"))
            provenance.append(ProvenanceEntry("years_experience", "computed",
                                              "derived:experience_span"))

    provenance = _dedup_provenance(provenance)
    overall = C.rounded(sum(field_conf.values()) / len(field_conf)) if field_conf else 0.0

    return CanonicalProfile(
        candidate_id=_candidate_id(emails, links, full_name),
        full_name=full_name, emails=emails, phones=phones, location=location,
        links=links, headline=headline, years_experience=years, skills=skills,
        experience=experience, education=education, provenance=provenance,
        overall_confidence=overall, field_confidence=field_conf,
    )


def _scalar_key(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def _resolve_scalar(field: str, entries: list[dict]):
    """Pick a single winner among competing values for a scalar field."""
    if not entries:
        return None, 0.0, []
    groups: dict[Any, list[dict]] = defaultdict(list)
    for e in entries:
        groups[_scalar_key(e["value"])].append(e)

    scored = []
    for key, members in groups.items():
        weights = [C.trust(m["source"]) for m in members]
        score = C.combine_agreement(weights)
        best_priority = min(C.priority(m["source"]) for m in members)
        scored.append((score, -best_priority, key, members))
    # winner: highest score, then best (lowest) priority, then lexical key
    scored.sort(key=lambda t: (-t[0], -t[1], str(t[2])))
    win_score, _, _, winners = scored[0]
    had_conflict = len(scored) > 1
    conf = C.rounded(C.conflict_penalty(win_score, had_conflict))
    prov = [ProvenanceEntry(field, m["source"], m["method"]) for m in winners]
    return winners[0]["value"], conf, prov


def _resolve_multi(field: str, entries: list[dict]):
    """Union + dedupe a multi-value scalar field (emails/phones/links.other)."""
    if not entries:
        return [], 0.0, []
    groups: dict[Any, list[dict]] = defaultdict(list)
    for e in entries:
        groups[_scalar_key(e["value"])].append(e)

    ranked = []
    for members in groups.values():
        best_trust = max(C.trust(m["source"]) for m in members)
        conf = C.combine_agreement([C.trust(m["source"]) for m in members])
        ranked.append((conf, best_trust, members[0]["value"]))
    # best-supported value first (so emails[0]/phones[0] is the strongest primary):
    # by combined confidence, then single-source trust, then lexical for determinism.
    ranked.sort(key=lambda t: (-t[0], -t[1], str(t[2])))

    values = [r[2] for r in ranked]
    conf = C.rounded(sum(r[0] for r in ranked) / len(ranked))
    prov = [ProvenanceEntry(field, e["source"], e["method"]) for e in entries]
    return values, conf, prov


def _resolve_skills(entries: list[dict], provenance: list, field_conf: dict) -> list[Skill]:
    if not entries:
        return []
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        groups[e["value"]].append(e)

    skills = []
    for name, members in groups.items():
        sources = sorted({m["source"] for m in members}, key=C.priority)
        recognized = any(m.get("recognized") for m in members)
        base = C.combine_agreement([C.trust(s) for s in sources])
        conf = C.rounded(base * C.skill_factor(recognized))
        skills.append(Skill(name=name, confidence=conf, sources=sources))
    skills.sort(key=lambda s: (-s.confidence, s.name))

    field_conf["skills"] = C.rounded(sum(s.confidence for s in skills) / len(skills))
    for e in entries:
        provenance.append(ProvenanceEntry("skills", e["source"], e["method"]))
    return skills


def _resolve_objects(field, entries, provenance, field_conf, key, builder, order):
    """Generic merge for experience/education: dedupe by key, merge fields by trust."""
    if not entries:
        return []
    groups: dict[Any, list[dict]] = defaultdict(list)
    for e in entries:
        groups[key(e["value"])].append(e)

    confs, objs = [], []
    for members in groups.values():
        # highest-trust source first so its non-null fields win the merge
        members = sorted(members, key=lambda m: -C.trust(m["source"]))
        merged: dict[str, Any] = {}
        for m in members:
            for k, v in m["value"].items():
                if v is not None and merged.get(k) is None:
                    merged[k] = v
        objs.append(builder(merged))
        confs.append(C.combine_agreement([C.trust(m["source"]) for m in members]))
    objs.sort(key=order)

    field_conf[field] = C.rounded(sum(confs) / len(confs))
    for e in entries:
        provenance.append(ProvenanceEntry(field, e["source"], e["method"]))
    return objs


def _build_experience(d: dict) -> Experience:
    return Experience(company=d.get("company"), title=d.get("title"),
                      start=d.get("start"), end=d.get("end"), summary=d.get("summary"))


def _build_education(d: dict) -> Education:
    return Education(institution=d.get("institution"), degree=d.get("degree"),
                     field=d.get("field"), end_year=d.get("end_year"))


def _experience_sort_key(e: Experience):
    # most recent first; missing start sorts last
    return (e.start is None, _neg_date(e.start), e.company or "")


def _neg_date(ym: str | None) -> str:
    # invert YYYY-MM so descending sort puts newer first via ascending compare
    if not ym:
        return ""
    return "".join(chr(ord("9") - int(c)) if c.isdigit() else c for c in ym)


def _derive_years(experience: list[Experience]) -> int | None:
    """Span from earliest start to latest end — only when fully determinable.

    Skipped if the latest role is open-ended ("present"), because that needs the
    current date and would break determinism. Never invents.
    """
    starts = [e.start[:4] for e in experience if e.start]
    ends = [e.end[:4] for e in experience if e.end]
    has_open = any(e.start and e.end is None for e in experience)
    if not starts or not ends or has_open:
        return None
    span = int(max(ends)) - int(min(starts))
    return span if span > 0 else None


def _lc(value):
    return value.strip().lower() if isinstance(value, str) else ""


def _dedup_provenance(entries: list[ProvenanceEntry]) -> list[ProvenanceEntry]:
    seen, out = set(), []
    for p in entries:
        sig = (p.field, p.source, p.method)
        if sig not in seen:
            seen.add(sig)
            out.append(p)
    out.sort(key=lambda p: (_FIELD_INDEX.get(p.field, 99), C.priority(p.source), p.method))
    return out


def _candidate_id(emails: list[str], links: Links, full_name: str | None) -> str:
    if emails:
        anchor = "email:" + emails[0]
    elif links.github:
        anchor = "gh:" + links.github.lower()
    elif links.linkedin:
        anchor = "li:" + links.linkedin.lower()
    elif full_name:
        anchor = "name:" + full_name.strip().lower()
    else:
        anchor = "unknown"
    digest = hashlib.sha1(anchor.encode("utf-8")).hexdigest()[:12]
    return f"cand_{digest}"
