"""End-to-end orchestration:

    ingest sources -> extract claims -> resolve entities -> merge -> project -> validate

Robust by construction: a missing/garbage source is caught and recorded as a
warning; the run continues with whatever sources did parse. The result carries the
projected profiles, the internal canonical records (for inspection/explainability),
plus any warnings and validation errors.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .config import OutputConfig, default_config
from .merge import merge_cluster, resolve_entities
from .models import CanonicalProfile
from .projection import project
from .sources import load_source
from .sources.base import SourceError
from .validation import validate


@dataclass
class PipelineResult:
    profiles: list[dict] = field(default_factory=list)  # projected + validated outputs
    canonical: list[CanonicalProfile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # schema-validation failures


def run(sources: list[dict], config: OutputConfig | None = None) -> PipelineResult:
    cfg = config or default_config()
    warnings: list[str] = []

    records = []
    for spec in sources:
        label = spec.get("type") or spec.get("path") or spec.get("url") or "<source>"
        try:
            records.extend(load_source(spec, warnings))
        except SourceError as exc:
            warnings.append(f"source {label}: {exc}")
        except Exception as exc:  # last-resort guard — never crash the whole run
            warnings.append(f"source {label}: unexpected error: {exc}")

    result = PipelineResult(warnings=warnings)
    for cluster in resolve_entities(records):
        profile = merge_cluster(cluster)
        proj = project(profile, cfg)
        errors = proj.errors + validate(proj.output, cfg)
        result.canonical.append(profile)
        result.profiles.append(proj.output)
        result.errors.extend(f"{profile.candidate_id}: {e}" for e in errors)
    return result


def load_manifest(path: str) -> list[dict]:
    """Load a manifest JSON and resolve each source path relative to the manifest."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    sources = data.get("sources", data) if isinstance(data, dict) else data
    if not isinstance(sources, list):
        raise ValueError("manifest must contain a 'sources' list")
    base = os.path.dirname(os.path.abspath(path))
    resolved = []
    for spec in sources:
        spec = dict(spec)
        for key in ("path", "fixture"):
            if spec.get(key) and not os.path.isabs(spec[key]):
                spec[key] = os.path.normpath(os.path.join(base, spec[key]))
        resolved.append(spec)
    return resolved


def dumps(profiles: list[dict], pretty: bool = True) -> str:
    """Serialize results: a single object for one candidate, else a list."""
    payload = profiles[0] if len(profiles) == 1 else profiles
    return json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False)
