"""GitHub profile — an unstructured source backed by a public REST API.

Input is a profile URL (``https://github.com/<user>``). Data comes from either:

* a local **fixture** JSON (``spec["fixture"]``) — used for the sample run and tests
  so the pipeline stays deterministic and offline, OR
* a **live** fetch of the public REST API (``spec["live"] = true``).

Fixture/response shape: ``{"user": {...github user...}, "repos": [{...}, ...]}``,
or a bare GitHub user object. Skills are derived from repository languages.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from ..models import SourceRecord
from .base import SourceError, parse_location, read_text_file

SOURCE_ID = "github"
_API = "https://api.github.com"


def _username(spec: dict) -> str | None:
    if spec.get("username"):
        return spec["username"]
    url = spec.get("url") or ""
    m = re.search(r"github\.com/([A-Za-z0-9\-]+)", url, re.I)
    return m.group(1) if m else None


def parse(spec: dict, warnings: list[str]) -> list[SourceRecord]:
    user_obj, repos = _load(spec, warnings)
    if user_obj is None:
        return []

    login = user_obj.get("login") or _username(spec) or ""
    rec = SourceRecord(source=SOURCE_ID, record_id=f"github:{login}")

    rec.add("full_name", user_obj.get("name"), "github_api:name")
    rec.add("headline", user_obj.get("bio"), "github_api:bio")
    rec.add("emails", user_obj.get("email"), "github_api:email")
    if login:
        rec.add("links.github", f"https://github.com/{login}", "github_api:profile")
    blog = (user_obj.get("blog") or "").strip()
    if blog:
        rec.add("links.portfolio", blog, "github_api:blog")

    loc = parse_location(user_obj.get("location") or "")
    rec.add("location.city", loc["city"], "github_api:location")
    rec.add("location.region", loc["region"], "github_api:location")
    rec.add("location.country", loc["country"], "github_api:location")

    # Derive skills from repo languages (non-fork repos), most-used first.
    for lang in _languages(repos):
        rec.add("skills", lang, "github_api:repo_language")

    return [rec] if rec.claims else []


def _languages(repos: list) -> list[str]:
    counts: dict[str, int] = {}
    for repo in repos or []:
        if not isinstance(repo, dict) or repo.get("fork"):
            continue
        lang = repo.get("language")
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    # deterministic order: by count desc, then name asc
    return [name for name, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _load(spec: dict, warnings: list[str]) -> tuple[dict | None, list]:
    if spec.get("fixture"):
        text = read_text_file(spec["fixture"])
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SourceError(f"{SOURCE_ID}: invalid fixture JSON: {exc}") from exc
        if isinstance(data, dict) and "user" in data:
            return data.get("user"), data.get("repos") or []
        return data, []  # bare user object

    if spec.get("live"):
        return _fetch_live(spec, warnings)

    warnings.append(f"{SOURCE_ID}: no fixture and live=false; skipping")
    return None, []


def _fetch_live(spec: dict, warnings: list[str]) -> tuple[dict | None, list]:
    user = _username(spec)
    if not user:
        warnings.append(f"{SOURCE_ID}: could not parse username from {spec.get('url')!r}")
        return None, []
    try:
        user_obj = _get_json(f"{_API}/users/{user}")
        repos = _get_json(f"{_API}/users/{user}/repos?per_page=100&sort=pushed")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        # Network/auth/rate-limit failure must degrade gracefully, not crash.
        warnings.append(f"{SOURCE_ID}: live fetch failed for {user}: {exc}")
        return None, []
    return user_obj, repos if isinstance(repos, list) else []


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "candidate-transformer"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))
