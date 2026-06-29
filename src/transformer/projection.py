"""Projection layer — reshape a canonical profile per a runtime config.

This is strictly separate from the engine: it reads a finished
:class:`CanonicalProfile`, never claims. It resolves each configured ``from``
path against the canonical record, applies any per-field ``normalize``, honors the
``on_missing`` policy, and attaches confidence/provenance blocks when toggled on.

Path grammar for ``from``:
    ``full_name``            scalar
    ``location.country``     nested scalar
    ``emails[0]``            list index
    ``skills[].name``        map a subfield over a list  -> list
"""

from __future__ import annotations

import re
from typing import Any

from .config import ConfigError, OutputConfig
from .models import CanonicalProfile
from .normalize import country as country_norm
from .normalize import phone as phone_norm
from .normalize import skills as skills_norm


class ProjectionResult:
    def __init__(self, output: dict, errors: list[str]):
        self.output = output
        self.errors = errors


# ---------------------------------------------------------------------------
# Path resolution against the canonical dict
# ---------------------------------------------------------------------------

def _segments(path: str):
    segs = []
    for part in path.split("."):
        m = re.fullmatch(r"([A-Za-z0-9_]+)(?:\[(\d*)\])?", part)
        if not m:
            raise ConfigError(f"invalid path segment {part!r} in {path!r}")
        key, bracket = m.group(1), m.group(2)
        if bracket is None:
            segs.append((key, "plain"))
        elif bracket == "":
            segs.append((key, "map"))
        else:
            segs.append((key, ("index", int(bracket))))
    return segs


def resolve_path(data: Any, path: str) -> Any:
    return _resolve(data, _segments(path))


def _resolve(data: Any, segs) -> Any:
    if not segs:
        return data
    (key, mode), rest = segs[0], segs[1:]
    if not isinstance(data, dict):
        return None
    val = data.get(key)
    if mode == "plain":
        return _resolve(val, rest)
    if mode == "map":
        if val is None:
            return []
        items = val if isinstance(val, list) else [val]
        return [_resolve(el, rest) for el in items]
    if isinstance(mode, tuple) and mode[0] == "index":
        if isinstance(val, list) and mode[1] < len(val):
            return _resolve(val[mode[1]], rest)
        return None
    return None  # pragma: no cover


# ---------------------------------------------------------------------------
# Per-field normalization applied at projection time
# ---------------------------------------------------------------------------

def _normalize_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        out = [_normalize_one(v, kind) for v in value]
        return [v for v in out if v is not None]
    return _normalize_one(value, kind)


def _normalize_one(value: Any, kind: str) -> Any:
    if kind == "E164":
        return phone_norm.to_e164(str(value), None)
    if kind == "canonical":
        res = skills_norm.canonicalize(str(value))
        return res[0] if res else None
    if kind == "iso_country":
        return country_norm.to_iso_alpha2(str(value))
    if kind == "lower":
        return str(value).lower()
    if kind == "upper":
        return str(value).upper()
    raise ConfigError(f"unknown normalize kind: {kind!r}")


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

def project(profile: CanonicalProfile, config: OutputConfig) -> ProjectionResult:
    data = profile.to_dict()
    out: dict[str, Any] = {}
    errors: list[str] = []
    used_fields: set[str] = set()

    for spec in config.fields:
        value = resolve_path(data, spec.source_path)
        if spec.normalize:
            value = _normalize_value(value, spec.normalize)
        used_fields.add(_confidence_key(spec.source_path))

        if value is None:
            # `required` is enforced by the validation layer (single authority).
            # Here we only apply the on_missing policy for non-required fields.
            if spec.required:
                continue  # leave absent; validation reports it
            policy = spec.on_missing or config.on_missing
            if policy == "error":
                errors.append(
                    f"field {spec.path!r} (from {spec.source_path!r}) is missing "
                    f"and on_missing='error'"
                )
                continue
            if policy == "omit":
                continue
            _set_path(out, spec.path, None)  # null
            continue

        _set_path(out, spec.path, value)

    _attach_blocks(out, profile, config, used_fields)
    return ProjectionResult(out, errors)


def _attach_blocks(out: dict, profile: CanonicalProfile, config: OutputConfig,
                   used_fields: set[str]) -> None:
    if config.is_default:
        if config.include_provenance:
            out["provenance"] = [
                {"field": p.field, "source": p.source, "method": p.method}
                for p in profile.provenance
            ]
        if config.include_confidence:
            out["overall_confidence"] = profile.overall_confidence
        return

    # custom config: add explicit confidence map + filtered provenance
    if config.include_confidence:
        conf_map = {}
        for spec in config.fields:
            ckey = _confidence_key(spec.source_path)
            if ckey in profile.field_confidence:
                conf_map[spec.path] = profile.field_confidence[ckey]
        out["confidence"] = conf_map
        out["overall_confidence"] = profile.overall_confidence
    if config.include_provenance:
        out["provenance"] = [
            {"field": p.field, "source": p.source, "method": p.method}
            for p in profile.provenance if p.field in used_fields
        ]


def _confidence_key(source_path: str) -> str:
    """Map a `from` path to the canonical field key that owns its confidence.

    ``skills[].name`` -> ``skills``; ``emails[0]`` -> ``emails``;
    ``location.country`` -> ``location.country``; ``links.github`` -> ``links.github``.
    """
    parts = re.sub(r"\[\d*\]", "", source_path).split(".")
    if parts[0] in ("location", "links") and len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


def _set_path(out: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
