"""Merge engine tests: entity resolution, conflict resolution, confidence, dedup."""

from transformer.merge import merge_cluster, resolve_entities
from transformer.models import SourceRecord


def make_record(source, **fields):
    rec = SourceRecord(source=source, record_id=f"{source}-test")
    for field, value in fields.items():
        field = field.replace("__", ".")  # links__github -> links.github
        values = value if isinstance(value, list) else [value]
        for v in values:
            rec.add(field, v, f"test:{field}")
    return rec


class TestEntityResolution:
    def test_shared_email_clusters_together(self):
        a = make_record("recruiter_csv", emails="x@e.com", full_name="X")
        b = make_record("ats_json", emails="x@e.com", headline="Eng")
        clusters = resolve_entities([a, b])
        assert len(clusters) == 1

    def test_different_people_stay_separate(self):
        a = make_record("recruiter_csv", emails="x@e.com")
        b = make_record("recruiter_csv", emails="y@e.com")
        clusters = resolve_entities([a, b])
        assert len(clusters) == 2

    def test_name_alone_does_not_merge(self):
        # two "John Smith"s with no shared contact must not be fused
        a = make_record("resume", full_name="John Smith")
        b = make_record("resume", full_name="John Smith")
        clusters = resolve_entities([a, b])
        assert len(clusters) == 2

    def test_phone_anchor_links_records(self):
        a = make_record("recruiter_csv", phones="+14155550132")
        b = make_record("ats_json", phones="(415) 555-0132", emails="z@e.com")
        # same 10-digit tail -> one cluster
        assert len(resolve_entities([a, b])) == 1

    def test_same_name_different_people_multi_source(self):
        # Two different "John Doe"s, each spread across several structured +
        # unstructured sources. Each person's own records share a strong anchor
        # (A by email, B by github username); the two people share none. They must
        # consolidate per-person and stay segregated despite identical names.
        records = [
            # John Doe A — 3 sources, linked by his email
            make_record("recruiter_csv", full_name="John Doe",
                        emails="john.doe@alpha.com", phones="+14155550111",
                        skills=["Python", "Go"]),
            make_record("ats_json", full_name="John Doe",
                        emails="john.doe@alpha.com", headline="Backend Engineer"),
            make_record("resume", full_name="John Doe",
                        emails="john.doe@alpha.com", skills="Kubernetes"),
            # John Doe B — 2 sources, linked by his github username (different person)
            make_record("resume", full_name="John Doe",
                        links__github="https://github.com/johndoe-b", skills="Rust"),
            make_record("github", full_name="John Doe",
                        links__github="https://github.com/johndoe-b", skills="Rust"),
        ]
        clusters = resolve_entities(records)
        assert len(clusters) == 2  # not fused on the shared name

        profiles = [merge_cluster(c) for c in clusters]
        assert len({p.candidate_id for p in profiles}) == 2  # distinct identities

        a = next(p for p in profiles if p.emails == ["john.doe@alpha.com"])
        b = next(p for p in profiles if not p.emails)
        # A consolidated all three of his sources; B's data did not bleed in
        assert {s.name for s in a.skills} == {"Python", "Go", "Kubernetes"}
        assert a.phones == ["+14155550111"]
        # B is wholly its own person
        assert b.links.github == "https://github.com/johndoe-b"
        assert {s.name for s in b.skills} == {"Rust"}


class TestConflictResolution:
    def test_agreement_beats_lone_dissenter(self):
        # two trusted sources say "Priya Sharma"; github says "Priya S."
        recs = [
            make_record("recruiter_csv", emails="p@e.com", full_name="Priya Sharma"),
            make_record("ats_json", emails="p@e.com", full_name="Priya Sharma"),
            make_record("github", emails="p@e.com", full_name="Priya S."),
        ]
        profile = merge_cluster(recs)
        assert profile.full_name == "Priya Sharma"

    def test_higher_trust_wins_on_tie(self):
        recs = [
            make_record("recruiter_notes", emails="p@e.com", headline="Engineer"),
            make_record("ats_json", emails="p@e.com", headline="Senior Engineer"),
        ]
        profile = merge_cluster(recs)
        assert profile.headline == "Senior Engineer"  # ats outranks notes


class TestMultiValue:
    def test_phone_dedup_across_formats(self):
        recs = [
            make_record("recruiter_csv", emails="p@e.com", phones="+91-98765-43210",
                        location__country="India"),
            make_record("ats_json", emails="p@e.com", phones="98765 43210"),
            make_record("recruiter_notes", emails="p@e.com", phones="9876543210"),
        ]
        profile = merge_cluster(recs)
        assert profile.phones == ["+919876543210"]

    def test_most_corroborated_email_is_primary(self):
        recs = [
            make_record("ats_json", emails=["work@acme.com", "me@personal.com"]),
            make_record("recruiter_csv", emails="me@personal.com"),
            make_record("resume", emails="me@personal.com"),
        ]
        profile = merge_cluster(recs)
        assert profile.emails[0] == "me@personal.com"


class TestSkills:
    def test_canonical_dedup_and_confidence(self):
        recs = [
            make_record("ats_json", emails="p@e.com", skills=["Go", "Python"]),
            make_record("resume", emails="p@e.com", skills=["Golang"]),  # -> Go
            make_record("github", emails="p@e.com", skills=["Go"]),
        ]
        profile = merge_cluster(recs)
        names = {s.name for s in profile.skills}
        assert "Go" in names and "Golang" not in names
        go = next(s for s in profile.skills if s.name == "Go")
        assert set(go.sources) == {"ats_json", "resume", "github"}
        py = next(s for s in profile.skills if s.name == "Python")
        assert go.confidence > py.confidence  # 3 sources > 1 source

    def test_unknown_skill_lower_confidence(self):
        recs = [
            make_record("github", emails="p@e.com", skills=["Python"]),
            make_record("github", emails="p@e.com", skills=["Bash"]),  # unknown
        ]
        profile = merge_cluster(recs)
        known = next(s for s in profile.skills if s.name == "Python")
        unknown = next(s for s in profile.skills if s.name == "Bash")
        assert unknown.confidence < known.confidence


class TestDerivedYears:
    def test_derives_span_when_fully_dated(self):
        rec = make_record("ats_json", emails="p@e.com")
        rec.add("experience", {"company": "A", "title": "Eng",
                               "start": "2016-01", "end": "2020-01", "summary": None}, "test")
        profile = merge_cluster([rec])
        assert profile.years_experience == 4

    def test_skips_derivation_when_role_is_open_ended(self):
        rec = make_record("ats_json", emails="p@e.com")
        rec.add("experience", {"company": "A", "title": "Eng",
                               "start": "2016-01", "end": "Present", "summary": None}, "test")
        profile = merge_cluster([rec])
        # open-ended end needs "now" -> would break determinism -> we do not invent
        assert profile.years_experience is None

    def test_explicit_years_not_overridden(self):
        rec = make_record("ats_json", emails="p@e.com", years_experience="8")
        profile = merge_cluster([rec])
        assert profile.years_experience == 8
