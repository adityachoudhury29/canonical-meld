"""Phone normalization to E.164.

Rule from the spec: *unknown values become null, never invented.* So a number we
cannot confidently parse to a valid E.164 is dropped — we never emit a fabricated
or syntactically-valid-but-wrong number.
"""

from __future__ import annotations

from typing import Optional

import phonenumbers


def to_e164(raw: str, region_hint: Optional[str] = None) -> Optional[str]:
    """Return a valid E.164 string (``+14155550123``) or ``None``.

    ``region_hint`` is an ISO-3166 alpha-2 code used to interpret numbers written
    without a country code. International numbers (``+...``) ignore the hint.
    """
    if not raw or not raw.strip():
        return None
    candidate = raw.strip()
    # libphonenumber wants a region only for numbers lacking a leading '+'.
    region = None if candidate.startswith("+") else region_hint
    try:
        parsed = phonenumbers.parse(candidate, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
