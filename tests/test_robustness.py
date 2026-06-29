"""Robustness tests: a missing/garbage source must never crash the run, and
unknown values must become null/empty — never invented."""

from pathlib import Path

from transformer import run
from transformer.pipeline import dumps, load_manifest

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "samples"


def test_garbage_sources_do_not_change_clean_output():
    clean = run(load_manifest(str(SAMPLES / "manifest.json")))
    robust = run(load_manifest(str(SAMPLES / "manifest_robust.json")))
    assert robust.warnings  # the bad sources were reported
    assert dumps(robust.profiles) == dumps(clean.profiles)  # output unaffected


def test_missing_file_is_warned_not_raised():
    result = run([{"type": "ats_json", "path": "/no/such/file.json"}])
    assert result.profiles == []
    assert any("not found" in w for w in result.warnings)


def test_empty_source_list():
    result = run([])
    assert result.profiles == []


def test_unparseable_phone_dropped_not_faked(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("name,email,phone\nJane Doe,jane@e.com,call-me-maybe\n")
    result = run([{"type": "recruiter_csv", "path": str(csv)}])
    assert len(result.profiles) == 1
    assert result.profiles[0]["phones"] == []  # not invented


def test_malformed_json_does_not_crash(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not: valid json,,,")
    result = run([{"type": "ats_json", "path": str(bad)}])
    assert result.profiles == []
    assert any("JSON" in w or "json" in w for w in result.warnings)


def test_detect_routing(tmp_path):
    from transformer.sources import detect
    assert detect({"path": "x.csv"}) == "recruiter_csv"
    assert detect({"url": "https://github.com/octocat"}) == "github"
    assert detect({"path": "resume.pdf"}) == "resume"
