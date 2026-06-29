"""Skill canonicalization.

Maps the many ways people write a skill onto one canonical name. Unknown skills
are *not* discarded — they pass through in a cleaned, title-cased form but are
flagged ``recognized=False`` so the merge step can assign them lower confidence.
"""

from __future__ import annotations

import re
from typing import Optional

# alias (lower-cased, stripped) -> canonical display name
_ALIASES = {
    "js": "JavaScript", "javascript": "JavaScript", "ecmascript": "JavaScript",
    "java script": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "python3": "Python",
    "golang": "Go", "go": "Go",
    "c++": "C++", "cpp": "C++",
    "c#": "C#", "csharp": "C#", "c sharp": "C#",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "reactjs": "React", "react.js": "React", "react": "React",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "psql": "PostgreSQL",
    "gcp": "Google Cloud Platform", "google cloud": "Google Cloud Platform",
    "aws": "AWS", "amazon web services": "AWS",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "tf": "TensorFlow", "tensorflow": "TensorFlow",
    "pytorch": "PyTorch", "torch": "PyTorch",
    "sql": "SQL",
    "rest": "REST", "restful": "REST", "rest api": "REST", "rest apis": "REST",
    "apis": "REST", "api": "REST",
    "graphql": "GraphQL",
    "docker": "Docker",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "java": "Java", "rust": "Rust", "ruby": "Ruby", "scala": "Scala",
    "kotlin": "Kotlin", "swift": "Swift", "php": "PHP",
    "html": "HTML", "css": "CSS",
    "spark": "Apache Spark", "apache spark": "Apache Spark",
    "kafka": "Apache Kafka", "apache kafka": "Apache Kafka",
}

# canonical names recognized by the taxonomy (drives confidence)
KNOWN = set(_ALIASES.values())


def canonicalize(raw: str) -> Optional[tuple[str, bool]]:
    """Return ``(canonical_name, recognized)`` or ``None`` if empty.

    ``recognized`` is ``True`` when the skill maps to a known canonical name.
    """
    if not raw or not raw.strip():
        return None
    key = re.sub(r"\s+", " ", raw.strip().lower())
    if key in _ALIASES:
        return _ALIASES[key], True
    # Unknown skill: clean it up but mark unrecognized.
    cleaned = re.sub(r"\s+", " ", raw.strip())
    return cleaned, False
