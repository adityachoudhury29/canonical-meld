"""Runtime output configuration — the "configurable output" twist.

A config reshapes the emitted output *without touching the engine*. It declares:

* ``fields[]`` — each with an output ``path``, an optional ``from`` (canonical
  source path), a ``type``, ``required``, and per-field ``normalize`` / ``on_missing``.
* ``include_confidence`` / ``include_provenance`` — toggle those blocks.
* ``on_missing`` — global default for missing values: ``null | omit | error``.

When no config is supplied, :func:`default_config` returns a spec describing the
full canonical schema (the spec's fixed field set).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

VALID_ON_MISSING = {"null", "omit", "error"}
VALID_TYPES = {
    "string", "number", "integer", "boolean",
    "string[]", "number[]", "object", "object[]", "any",
}


class ConfigError(Exception):
    """Malformed runtime config."""


@dataclass
class FieldSpec:
    path: str  # output key (dotted paths build nested objects)
    from_path: Optional[str] = None  # canonical source path; defaults to `path`
    type: str = "any"
    required: bool = False
    normalize: Optional[str] = None
    on_missing: Optional[str] = None  # per-field override of the global policy

    @property
    def source_path(self) -> str:
        return self.from_path or self.path


@dataclass
class OutputConfig:
    fields: list[FieldSpec]
    include_confidence: bool = True
    include_provenance: bool = True
    on_missing: str = "null"
    is_default: bool = False  # the built-in full-schema config

    @staticmethod
    def from_dict(data: dict) -> "OutputConfig":
        if not isinstance(data, dict):
            raise ConfigError("config must be a JSON object")

        on_missing = data.get("on_missing", "null")
        if on_missing not in VALID_ON_MISSING:
            raise ConfigError(f"on_missing must be one of {sorted(VALID_ON_MISSING)}")

        raw_fields = data.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ConfigError("config.fields must be a non-empty list")

        fields_out = []
        seen_paths = set()
        for i, f in enumerate(raw_fields):
            if not isinstance(f, dict) or "path" not in f:
                raise ConfigError(f"fields[{i}] must be an object with a 'path'")
            spec = FieldSpec(
                path=f["path"],
                from_path=f.get("from"),
                type=f.get("type", "any"),
                required=bool(f.get("required", False)),
                normalize=f.get("normalize"),
                on_missing=f.get("on_missing"),
            )
            if spec.type not in VALID_TYPES:
                raise ConfigError(f"fields[{i}].type {spec.type!r} not in {sorted(VALID_TYPES)}")
            if spec.on_missing is not None and spec.on_missing not in VALID_ON_MISSING:
                raise ConfigError(f"fields[{i}].on_missing invalid: {spec.on_missing!r}")
            if spec.path in seen_paths:
                raise ConfigError(f"duplicate output path: {spec.path!r}")
            seen_paths.add(spec.path)
            fields_out.append(spec)

        return OutputConfig(
            fields=fields_out,
            include_confidence=bool(data.get("include_confidence", True)),
            include_provenance=bool(data.get("include_provenance", True)),
            on_missing=on_missing,
        )


def load_config(path: str) -> OutputConfig:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc
    return OutputConfig.from_dict(data)


def default_config() -> OutputConfig:
    """The full canonical schema, with provenance + confidence on."""
    specs = [
        FieldSpec("candidate_id", type="string", required=True),
        FieldSpec("full_name", type="string"),
        FieldSpec("emails", type="string[]"),
        FieldSpec("phones", type="string[]"),
        FieldSpec("location", type="object"),
        FieldSpec("links", type="object"),
        FieldSpec("headline", type="string"),
        FieldSpec("years_experience", type="number"),
        FieldSpec("skills", type="object[]"),
        FieldSpec("experience", type="object[]"),
        FieldSpec("education", type="object[]"),
    ]
    cfg = OutputConfig(fields=specs, include_confidence=True,
                       include_provenance=True, on_missing="null")
    cfg.is_default = True
    return cfg
