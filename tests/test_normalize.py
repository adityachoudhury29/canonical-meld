"""Normalizer unit tests: phones, dates, country, skills."""

from transformer.normalize import country, dates, phone, skills


class TestPhone:
    def test_international_to_e164(self):
        assert phone.to_e164("+91-98765-43210") == "+919876543210"

    def test_local_with_region_hint(self):
        assert phone.to_e164("98765 43210", "IN") == "+919876543210"
        assert phone.to_e164("(415) 555-0132", "US") == "+14155550132"

    def test_three_formats_converge(self):
        # the core dedup guarantee: different formats -> one canonical number
        a = phone.to_e164("+91-98765-43210")
        b = phone.to_e164("98765 43210", "IN")
        c = phone.to_e164("9876543210", "IN")
        assert a == b == c == "+919876543210"

    def test_unparseable_returns_none_not_fake(self):
        assert phone.to_e164("call me maybe") is None
        assert phone.to_e164("12345") is None
        assert phone.to_e164("") is None

    def test_local_number_without_region_is_dropped(self):
        # no country code and no hint -> we refuse to guess
        assert phone.to_e164("98765 43210", None) is None


class TestDates:
    def test_year_month_formats(self):
        assert dates.to_year_month("Jan 2020") == "2020-01"
        assert dates.to_year_month("January 2020") == "2020-01"
        assert dates.to_year_month("2020-1") == "2020-01"
        assert dates.to_year_month("01/2020") == "2020-01"
        assert dates.to_year_month("2020/03") == "2020-03"

    def test_year_only_kept_as_year(self):
        assert dates.to_year_month("2018") == "2018"

    def test_present_is_not_a_date(self):
        assert dates.is_present("Present") is True
        assert dates.is_present("current") is True
        assert dates.to_year_month("present") is None

    def test_garbage_returns_none(self):
        assert dates.to_year_month("sometime last spring") is None

    def test_to_year(self):
        assert dates.to_year("Class of 2018") == 2018
        assert dates.to_year("2020-05") == 2020


class TestCountry:
    def test_names_and_aliases(self):
        assert country.to_iso_alpha2("United States") == "US"
        assert country.to_iso_alpha2("USA") == "US"
        assert country.to_iso_alpha2("India") == "IN"
        assert country.to_iso_alpha2("UK") == "GB"

    def test_existing_codes(self):
        assert country.to_iso_alpha2("US") == "US"
        assert country.to_iso_alpha2("in") == "IN"

    def test_unknown_returns_none(self):
        assert country.to_iso_alpha2("Atlantis") is None
        assert country.to_iso_alpha2("") is None


class TestSkills:
    def test_aliases_canonicalize(self):
        assert skills.canonicalize("golang") == ("Go", True)
        assert skills.canonicalize("JS") == ("JavaScript", True)
        assert skills.canonicalize("k8s") == ("Kubernetes", True)
        assert skills.canonicalize("  python3 ") == ("Python", True)

    def test_unknown_skill_passes_through_unrecognized(self):
        name, recognized = skills.canonicalize("Underwater Basket Weaving")
        assert name == "Underwater Basket Weaving"
        assert recognized is False

    def test_empty_returns_none(self):
        assert skills.canonicalize("   ") is None
