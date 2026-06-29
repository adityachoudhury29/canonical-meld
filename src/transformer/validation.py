"""Validate a projected output against the requested schema.

The pipeline never returns an output that has not passed here. Two kinds of
checks: presence (``required`` fields must be present and non-null) and type
(each present value must match its declared ``type``). ``None`` is allowed for
non-required fields.
"""

from __future__ import annotations

from typing import Any

from .config import OutputConfig


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_TYPE_CHECKS = {
    "any": lambda v: True,
    "string": lambda v: isinstance(v, str),
    "number": _is_number,
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "string[]": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "number[]": lambda v: isinstance(v, list) and all(_is_number(x) for x in v),
    "object": lambda v: isinstance(v, dict),
    "object[]": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
}


def _get_path(out: dict, path: str):
    cur: Any = out
    present = True
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            present = False
            cur = None
            break
    return present, cur


def validate(output: dict, config: OutputConfig) -> list[str]:
    """Return a list of human-readable schema violations (empty == valid)."""
    errors: list[str] = []
    for spec in config.fields:
        present, value = _get_path(output, spec.path)
        if spec.required and (not present or value is None):
            errors.append(f"required field {spec.path!r} is missing or null")
            continue
        if not present or value is None:
            continue  # legitimately absent / null for a non-required field
        checker = _TYPE_CHECKS.get(spec.type, _TYPE_CHECKS["any"])
        if not checker(value):
            errors.append(
                f"field {spec.path!r} expected type {spec.type!r}, got "
                f"{type(value).__name__}"
            )
    return errors
