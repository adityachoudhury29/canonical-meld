"""Country normalization to ISO-3166 alpha-2.

A curated map covering common spellings/aliases plus alpha-3 codes. If a name is
not recognized we return ``None`` (honestly-empty) rather than guessing.
"""

from __future__ import annotations

from typing import Optional

# alpha-2 -> canonical alpha-2 (identity, but also defines the valid set)
_ALPHA2 = {
    "US", "GB", "CA", "IN", "AU", "DE", "FR", "IE", "NL", "SE", "ES", "IT",
    "PT", "BR", "MX", "AR", "SG", "JP", "CN", "KR", "IL", "AE", "ZA", "NZ",
    "CH", "BE", "AT", "DK", "NO", "FI", "PL", "RU", "UA", "PK", "BD", "LK",
    "PH", "ID", "MY", "TH", "VN", "TR", "EG", "NG", "KE",
}

# alias / spelling -> alpha-2
_NAME_TO_ALPHA2 = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "u.s.": "US", "u.s.a.": "US", "america": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB",
    "canada": "CA",
    "india": "IN", "bharat": "IN",
    "australia": "AU",
    "germany": "DE", "deutschland": "DE",
    "france": "FR",
    "ireland": "IE",
    "netherlands": "NL", "holland": "NL", "the netherlands": "NL",
    "sweden": "SE", "spain": "ES", "italy": "IT", "portugal": "PT",
    "brazil": "BR", "brasil": "BR", "mexico": "MX", "argentina": "AR",
    "singapore": "SG", "japan": "JP", "china": "CN", "south korea": "KR",
    "korea": "KR", "israel": "IL", "uae": "AE",
    "united arab emirates": "AE", "south africa": "ZA", "new zealand": "NZ",
    "switzerland": "CH", "belgium": "BE", "austria": "AT", "denmark": "DK",
    "norway": "NO", "finland": "FI", "poland": "PL", "russia": "RU",
    "ukraine": "UA", "pakistan": "PK", "bangladesh": "BD", "sri lanka": "LK",
    "philippines": "PH", "indonesia": "ID", "malaysia": "MY", "thailand": "TH",
    "vietnam": "VN", "turkey": "TR", "egypt": "EG", "nigeria": "NG", "kenya": "KE",
}

# common alpha-3 -> alpha-2
_ALPHA3_TO_ALPHA2 = {
    "USA": "US", "GBR": "GB", "CAN": "CA", "IND": "IN", "AUS": "AU",
    "DEU": "DE", "FRA": "FR", "IRL": "IE", "NLD": "NL", "SWE": "SE",
    "ESP": "ES", "ITA": "IT", "PRT": "PT", "BRA": "BR", "MEX": "MX",
    "SGP": "SG", "JPN": "JP", "CHN": "CN", "KOR": "KR", "ISR": "IL",
    "ARE": "AE", "ZAF": "ZA", "NZL": "NZ", "CHE": "CH",
}


def to_iso_alpha2(raw: str) -> Optional[str]:
    """Map a country name/code to ISO-3166 alpha-2, or ``None`` if unrecognized."""
    if not raw or not raw.strip():
        return None
    token = raw.strip()
    upper = token.upper()
    if len(upper) == 2 and upper in _ALPHA2:
        return upper
    if len(upper) == 3 and upper in _ALPHA3_TO_ALPHA2:
        return _ALPHA3_TO_ALPHA2[upper]
    return _NAME_TO_ALPHA2.get(token.lower())
