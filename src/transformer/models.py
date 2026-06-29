"""Core data models.

Two layers live here, deliberately kept apart:

* The *claim* layer  — what each source actually said (``Claim`` / ``SourceRecord``).
  Every value a source provides is captured as a typed claim that remembers where
  it came from and how it was obtained. This is the raw material for merging.

* The *canonical* layer — the single, normalized, deduplicated profile we emit
  (``CanonicalProfile`` and its nested objects). This is what downstream consumes.

The projection layer (see ``projection.py``) reshapes the canonical profile per a
runtime config; it never reaches back into claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Claim layer — what a source said
# ---------------------------------------------------------------------------

# Canonical field paths a claim may target. List-valued fields accumulate;
# scalar fields compete for a single winner.
SCALAR_FIELDS = {
    "full_name",
    "headline",
    "years_experience",
    "location.city",
    "location.region",
    "location.country",
    "links.linkedin",
    "links.github",
    "links.portfolio",
}
MULTI_FIELDS = {
    "emails",
    "phones",
    "links.other",
    "skills",
    "experience",
    "education",
}
ALL_CLAIM_FIELDS = SCALAR_FIELDS | MULTI_FIELDS


@dataclass(frozen=True)
class Claim:
    """One assertion from one source.

    ``field``   canonical path the claim targets (e.g. ``"emails"``, ``"location.country"``).
    ``value``   the asserted value. For multi-value object fields (experience,
                education) this is a ``dict``; for skills it is the skill name ``str``.
    ``source``  source type id (e.g. ``"recruiter_csv"``, ``"github"``).
    ``method``  how it was extracted (e.g. ``"csv_column:email"``, ``"regex:email"``).
                Pure traceability — it is what makes a field *explainable*.
    """

    field: str
    value: Any
    source: str
    method: str

    def __post_init__(self) -> None:
        if self.field not in ALL_CLAIM_FIELDS:
            raise ValueError(f"unknown claim field: {self.field!r}")


@dataclass
class SourceRecord:
    """All claims about one person from one source instance (e.g. one CSV row)."""

    source: str
    record_id: str
    claims: list[Claim] = field(default_factory=list)

    def add(self, fieldname: str, value: Any, method: str) -> None:
        """Append a claim, silently skipping empty values (never invent)."""
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        self.claims.append(
            Claim(field=fieldname, value=value, source=self.source, method=method)
        )


# ---------------------------------------------------------------------------
# Canonical layer — the trustworthy profile
# ---------------------------------------------------------------------------


@dataclass
class Location:
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2


@dataclass
class Links:
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: list[str] = field(default_factory=list)


@dataclass
class Skill:
    name: str
    confidence: float
    sources: list[str] = field(default_factory=list)


@dataclass
class Experience:
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None  # YYYY-MM or None for "present"
    summary: Optional[str] = None


@dataclass
class Education:
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None


@dataclass
class ProvenanceEntry:
    field: str
    source: str
    method: str


@dataclass
class CanonicalProfile:
    candidate_id: str
    full_name: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: Location = field(default_factory=Location)
    links: Links = field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[Skill] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    overall_confidence: float = 0.0

    # Internal only — not part of the default emitted schema. Maps a canonical
    # field path to its computed confidence so the projection layer can attach
    # per-field confidence when a custom config asks for it.
    field_confidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the *default* canonical schema (the spec's fixed field set).

        ``field_confidence`` is intentionally excluded — it is bookkeeping.
        """
        return {
            "candidate_id": self.candidate_id,
            "full_name": self.full_name,
            "emails": list(self.emails),
            "phones": list(self.phones),
            "location": {
                "city": self.location.city,
                "region": self.location.region,
                "country": self.location.country,
            },
            "links": {
                "linkedin": self.links.linkedin,
                "github": self.links.github,
                "portfolio": self.links.portfolio,
                "other": list(self.links.other),
            },
            "headline": self.headline,
            "years_experience": self.years_experience,
            "skills": [
                {"name": s.name, "confidence": s.confidence, "sources": list(s.sources)}
                for s in self.skills
            ],
            "experience": [
                {
                    "company": e.company,
                    "title": e.title,
                    "start": e.start,
                    "end": e.end,
                    "summary": e.summary,
                }
                for e in self.experience
            ],
            "education": [
                {
                    "institution": ed.institution,
                    "degree": ed.degree,
                    "field": ed.field,
                    "end_year": ed.end_year,
                }
                for ed in self.education
            ],
            "provenance": [
                {"field": p.field, "source": p.source, "method": p.method}
                for p in self.provenance
            ],
            "overall_confidence": self.overall_confidence,
        }
