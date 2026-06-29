"""Schema-validation tests for the projection output."""

from transformer.config import OutputConfig
from transformer.validation import validate


def cfg(fields):
    return OutputConfig.from_dict({"fields": fields})


def test_valid_output_has_no_errors():
    c = cfg([{"path": "full_name", "type": "string", "required": True},
             {"path": "skills", "type": "string[]"}])
    assert validate({"full_name": "Priya", "skills": ["Go", "Python"]}, c) == []


def test_type_mismatch_reported():
    c = cfg([{"path": "full_name", "type": "string"}])
    errors = validate({"full_name": 123}, c)
    assert errors and "expected type 'string'" in errors[0]


def test_required_missing_reported():
    c = cfg([{"path": "email", "type": "string", "required": True}])
    assert validate({}, c)
    assert validate({"email": None}, c)


def test_string_array_rejects_non_strings():
    c = cfg([{"path": "skills", "type": "string[]"}])
    assert validate({"skills": ["ok", 7]}, c)


def test_null_allowed_for_optional():
    c = cfg([{"path": "headline", "type": "string"}])
    assert validate({"headline": None}, c) == []


def test_nested_path_lookup():
    c = cfg([{"path": "location.country", "type": "string", "required": True}])
    assert validate({"location": {"country": "IN"}}, c) == []
    assert validate({"location": {}}, c)  # required nested missing
