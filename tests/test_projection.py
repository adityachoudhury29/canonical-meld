"""Projection + path-resolution tests for the configurable-output layer."""

import pytest

from transformer.config import ConfigError, OutputConfig
from transformer.models import (
    CanonicalProfile, Education, Experience, Links, Location, Skill,
)
from transformer.projection import project, resolve_path


def sample_profile():
    return CanonicalProfile(
        candidate_id="cand_x",
        full_name="Priya Sharma",
        emails=["me@e.com", "work@acme.com"],
        phones=["+919876543210"],
        location=Location(city="Bengaluru", region="Karnataka", country="IN"),
        links=Links(linkedin="https://linkedin.com/in/p", github="https://github.com/p"),
        headline="Senior Backend Engineer",
        years_experience=7,
        skills=[Skill("Go", 0.99, ["ats_json"]), Skill("Python", 0.9, ["github"])],
        experience=[Experience("Acme Corp", "Senior Backend Engineer", "2021-03", None, None)],
        education=[Education("IIT Bombay", "B.Tech", "CS", 2018)],
        overall_confidence=0.9,
        field_confidence={"full_name": 0.9, "emails": 0.95, "phones": 0.98,
                          "skills": 0.94, "location.country": 0.99},
    )


class TestResolvePath:
    def setup_method(self):
        self.data = sample_profile().to_dict()

    def test_index(self):
        assert resolve_path(self.data, "emails[0]") == "me@e.com"

    def test_map_over_list(self):
        assert resolve_path(self.data, "skills[].name") == ["Go", "Python"]

    def test_nested_scalar(self):
        assert resolve_path(self.data, "location.country") == "IN"
        assert resolve_path(self.data, "links.github") == "https://github.com/p"

    def test_index_then_field(self):
        assert resolve_path(self.data, "experience[0].title") == "Senior Backend Engineer"

    def test_out_of_range_and_missing(self):
        assert resolve_path(self.data, "phones[5]") is None
        assert resolve_path(self.data, "nope") is None


class TestProjection:
    def test_rename_and_flatten(self):
        cfg = OutputConfig.from_dict({
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
                {"path": "skills", "from": "skills[].name", "type": "string[]"},
            ],
            "include_provenance": False,
        })
        result = project(sample_profile(), cfg)
        assert result.errors == []
        assert result.output["primary_email"] == "me@e.com"
        assert result.output["skills"] == ["Go", "Python"]
        assert "provenance" not in result.output
        assert "confidence" in result.output  # on by default

    def test_normalize_at_projection(self):
        cfg = OutputConfig.from_dict({
            "fields": [
                {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
                {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"},
            ],
        })
        out = project(sample_profile(), cfg).output
        assert out["phone"] == "+919876543210"
        assert out["skills"] == ["Go", "Python"]

    def test_on_missing_null(self):
        cfg = OutputConfig.from_dict({
            "fields": [{"path": "portfolio", "from": "links.portfolio", "type": "string"}],
            "on_missing": "null",
        })
        out = project(sample_profile(), cfg).output
        assert out["portfolio"] is None

    def test_on_missing_omit(self):
        cfg = OutputConfig.from_dict({
            "fields": [{"path": "portfolio", "from": "links.portfolio", "type": "string"}],
            "on_missing": "omit",
        })
        out = project(sample_profile(), cfg).output
        assert "portfolio" not in out

    def test_on_missing_error(self):
        cfg = OutputConfig.from_dict({
            "fields": [{"path": "portfolio", "from": "links.portfolio", "type": "string",
                        "on_missing": "error"}],
        })
        result = project(sample_profile(), cfg)
        assert result.errors and "portfolio" in result.errors[0]

    def test_toggles_off(self):
        cfg = OutputConfig.from_dict({
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": False,
            "include_provenance": False,
        })
        out = project(sample_profile(), cfg).output
        assert "confidence" not in out and "overall_confidence" not in out
        assert "provenance" not in out


class TestConfigValidation:
    def test_rejects_bad_type(self):
        with pytest.raises(ConfigError):
            OutputConfig.from_dict({"fields": [{"path": "x", "type": "blob"}]})

    def test_rejects_duplicate_paths(self):
        with pytest.raises(ConfigError):
            OutputConfig.from_dict({"fields": [{"path": "x"}, {"path": "x"}]})

    def test_rejects_empty_fields(self):
        with pytest.raises(ConfigError):
            OutputConfig.from_dict({"fields": []})
