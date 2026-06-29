"""End-to-end gold-profile tests against the bundled sample inputs.

These pin the behaviour that matters: cross-source dedup, conflict winners,
skill canonicalization, E.164, provenance/confidence, and the configurable output.
"""

from pathlib import Path

import pytest

from transformer import load_config, run
from transformer.pipeline import dumps, load_manifest

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "samples"
CONFIGS = REPO / "configs"


@pytest.fixture(scope="module")
def default_result():
    return run(load_manifest(str(SAMPLES / "manifest.json")))


def _find(profiles, name):
    return next(p for p in profiles if p["full_name"] == name)


def test_two_candidates_and_no_validation_errors(default_result):
    assert len(default_result.profiles) == 2
    assert default_result.errors == []


class TestGoldPriya:
    @pytest.fixture(autouse=True)
    def _setup(self, default_result):
        self.p = _find(default_result.profiles, "Priya Sharma")

    def test_primary_email_is_most_corroborated(self):
        assert self.p["emails"][0] == "priya.sharma@example.com"
        assert "p.sharma@acme.com" in self.p["emails"]

    def test_phone_deduped_to_single_e164(self):
        assert self.p["phones"] == ["+919876543210"]

    def test_location_conflict_resolved_to_agreed_city(self):
        # CSV+ATS+GitHub say Bengaluru; resume says Bangalore -> agreement wins
        assert self.p["location"]["city"] == "Bengaluru"
        assert self.p["location"]["country"] == "IN"

    def test_headline_from_highest_trust_source(self):
        # ATS "Senior Backend Engineer" beats resume "Backend Engineer"
        assert self.p["headline"] == "Senior Backend Engineer"

    def test_years_experience(self):
        assert self.p["years_experience"] == 7

    def test_skills_canonicalized_and_merged(self):
        names = {s["name"] for s in self.p["skills"]}
        # JS -> JavaScript, Golang/Go -> Go, k8s -> Kubernetes
        assert {"Go", "Python", "Kubernetes", "JavaScript", "PostgreSQL"} <= names
        assert "Golang" not in names and "k8s" not in names and "JS" not in names
        go = next(s for s in self.p["skills"] if s["name"] == "Go")
        assert set(go["sources"]) == {"ats_json", "resume", "github"}

    def test_experience_merged_and_ordered(self):
        titles = [e["title"] for e in self.p["experience"]]
        assert titles == ["Senior Backend Engineer", "Backend Engineer"]
        assert self.p["experience"][0]["company"] == "Acme Corp"
        assert self.p["experience"][0]["end"] is None  # "Present"

    def test_education_normalized(self):
        edu = self.p["education"][0]
        assert edu["institution"] == "IIT Bombay"
        assert edu["end_year"] == 2018

    def test_provenance_and_confidence_present(self):
        assert self.p["provenance"]
        assert self.p["overall_confidence"] > 0.8
        # every emitted field traces to a source+method
        assert all({"field", "source", "method"} <= set(e) for e in self.p["provenance"])


class TestSparseCandidate:
    def test_marcus_only_from_csv(self, default_result):
        m = _find(default_result.profiles, "Marcus Lee")
        assert m["phones"] == ["+14155550132"]
        assert m["skills"] == []
        assert m["links"]["github"] is None  # not invented
        assert m["overall_confidence"] == 0.85


class TestCustomConfig:
    def test_recruiter_view_shape(self):
        cfg = load_config(str(CONFIGS / "recruiter_view.json"))
        result = run(load_manifest(str(SAMPLES / "manifest.json")), cfg)
        p = _find(result.profiles, "Priya Sharma")
        assert p["primary_email"] == "priya.sharma@example.com"
        assert p["phone"] == "+919876543210"
        assert p["current_title"] == "Senior Backend Engineer"
        assert p["country"] == "IN"
        assert isinstance(p["skills"], list) and all(isinstance(s, str) for s in p["skills"])
        assert "confidence" in p  # include_confidence: true
        assert "provenance" not in p  # include_provenance: false
        assert result.errors == []

    def test_contacts_min_omits_missing(self):
        cfg = load_config(str(CONFIGS / "contacts_min.json"))
        result = run(load_manifest(str(SAMPLES / "manifest.json")), cfg)
        # this config renames full_name -> name
        marcus = next(p for p in result.profiles if p["name"] == "Marcus Lee")
        assert "linkedin" not in marcus  # omitted (on_missing: omit)
        assert "confidence" not in marcus


def test_deterministic_output():
    sources = load_manifest(str(SAMPLES / "manifest.json"))
    assert dumps(run(sources).profiles) == dumps(run(sources).profiles)
