"""Canonical profile builder.

Turns messy, overlapping candidate sources into one canonical, normalized,
deduplicated profile with provenance and confidence — and projects it to any
runtime-configured output shape.
"""

from .config import OutputConfig, default_config, load_config
from .pipeline import PipelineResult, run

__version__ = "0.1.0"
__all__ = ["run", "PipelineResult", "OutputConfig", "default_config", "load_config"]
