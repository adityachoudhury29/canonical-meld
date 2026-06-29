"""Free-text helpers shared by the unstructured adapters (resume, notes, GitHub bio).

These extract candidate signals (emails, phones, URLs) from prose. They are
deliberately conservative: a miss yields nothing rather than a wrong value.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Loose phone matcher for free text; real validation happens in phone.to_e164,
# which rejects anything that is not a valid number.
PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().\-]{7,16}\d)(?!\w)")

_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)", re.I)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9\-]+)", re.I)


def clean(value: str) -> str:
    """Collapse whitespace and trim."""
    return re.sub(r"\s+", " ", (value or "")).strip()


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_url(value: str) -> str:
    v = (value or "").strip()
    if v and not re.match(r"^https?://", v, re.I):
        v = "https://" + v
    return v.rstrip("/")


def extract_emails(text: str) -> list[str]:
    seen, out = set(), []
    for m in EMAIL_RE.findall(text or ""):
        e = normalize_email(m)
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def extract_phones(text: str) -> list[str]:
    return [m.strip() for m in PHONE_RE.findall(text or "")]


def linkedin_username(text: str) -> str | None:
    m = _LINKEDIN_RE.search(text or "")
    return m.group(1) if m else None


def github_username(text: str) -> str | None:
    m = _GITHUB_RE.search(text or "")
    if not m:
        return None
    # Skip non-profile paths like github.com/orgs/... when they slip through.
    user = m.group(1)
    return None if user.lower() in {"orgs", "about", "features"} else user
