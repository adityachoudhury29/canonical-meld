"""Shared helpers for source adapters.

Each adapter exposes ``SOURCE_ID`` and ``parse(spec, warnings) -> list[SourceRecord]``
and emits **raw** claims (values are normalized later, centrally, in ``merge.py``,
where cross-source context such as the resolved country is available). A hard
failure (missing file, invalid JSON) raises :class:`SourceError`; the pipeline
catches it so one bad source never crashes the run. Soft problems (a single
unparseable row) are skipped — never invented.
"""

from __future__ import annotations

import os
import re

from ..normalize import country as country_norm


class SourceError(Exception):
    """A source could not be parsed at all (missing file, invalid JSON, ...)."""


def read_text_file(path: str) -> str:
    if not os.path.exists(path):
        raise SourceError(f"file not found: {path}")
    if os.path.isdir(path):
        raise SourceError(f"expected a file but got a directory: {path}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:  # pragma: no cover - filesystem edge
        raise SourceError(f"cannot read {path}: {exc}") from exc


def split_multi(value: str) -> list[str]:
    """Split a cell that may hold several values (``a@x.com; b@y.com``)."""
    if not value:
        return []
    parts = re.split(r"[;,/|]", value)
    return [p.strip() for p in parts if p.strip()]


def parse_location(value: str) -> dict[str, str | None]:
    """Best-effort split of a free-form location into city / region / country.

    Returns raw tokens (final normalization happens in merge). Country placement
    is decided by whether a token maps to a known country code.
    """
    out: dict[str, str | None] = {"city": None, "region": None, "country": None}
    if not value or not value.strip():
        return out
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        return out
    if len(parts) == 1:
        only = parts[0]
        if country_norm.to_iso_alpha2(only):
            out["country"] = only
        else:
            out["city"] = only
        return out
    # 2+ parts: last token is country if it resolves, else treat as region.
    if country_norm.to_iso_alpha2(parts[-1]):
        out["country"] = parts[-1]
        rest = parts[:-1]
    else:
        rest = parts
    if rest:
        out["city"] = rest[0]
    if len(rest) >= 2:
        out["region"] = rest[1]
    return out
