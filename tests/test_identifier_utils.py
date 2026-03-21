# Copyright (c) 2026 purego-gen contributors.

"""Tests for identifier validation utilities."""

from __future__ import annotations

from purego_gen.identifier_utils import (
    accessor_getter_name,
    accessor_setter_name,
    validate_generated_names,
)


def test_accessor_getter_name_preserves_c_name() -> None:
    """Getter name should preserve the original C field name."""
    assert accessor_getter_name("year") == "Get_year"
    assert accessor_getter_name("deprecated_data") == "Get_deprecated_data"


def test_accessor_setter_name_preserves_c_name() -> None:
    """Setter name should preserve the original C field name."""
    assert accessor_setter_name("year") == "Set_year"
    assert accessor_setter_name("deprecated_data") == "Set_deprecated_data"


def test_validate_generated_names_no_collision_single_entry() -> None:
    """Single entry should produce no errors."""
    names = [("add", "function from C symbol 'add'", True)]
    errors = validate_generated_names(names)
    assert not errors


def test_validate_generated_names_detects_cross_category_collision() -> None:
    """Duplicate generated names across categories should be reported."""
    names = [
        ("status", "function from C symbol 'status'", True),
        ("status", "constant", True),
    ]
    errors = validate_generated_names(names)
    assert any("collides with" in e for e in errors)


def test_validate_generated_names_detects_go_keyword_collision() -> None:
    """Generated names matching Go keywords should be reported."""
    names = [("type", "type from C symbol 'type'", True)]
    errors = validate_generated_names(names)
    assert any("Go keyword" in e for e in errors)


def test_validate_generated_names_detects_go_predeclared_shadowing() -> None:
    """Generated names matching Go predeclared identifiers should be reported."""
    names = [("len", "function from C symbol 'len'", True)]
    errors = validate_generated_names(names)
    assert any("predeclared" in e for e in errors)


def test_validate_generated_names_detects_import_shadowing() -> None:
    """Generated names matching import names should be reported."""
    names = [("purego", "function from C symbol 'purego'", True)]
    errors = validate_generated_names(names)
    assert any("import name" in e for e in errors)


def test_validate_generated_names_passes_for_safe_names() -> None:
    """Normal non-colliding names should produce no errors."""
    names = [
        ("add", "function from C symbol 'add'", True),
        ("mode_t", "type from C typedef", True),
        ("STATUS_OK", "constant", True),
    ]
    errors = validate_generated_names(names)
    assert not errors


def test_validate_generated_names_detects_multiple_errors() -> None:
    """Multiple issues should all be reported."""
    names = [
        ("type", "type from C symbol 'type'", True),
        ("len", "function from C symbol 'len'", True),
        ("purego", "constant", True),
    ]
    errors = validate_generated_names(names)
    # Each entry should produce at least one error.
    assert len(errors) >= len(names)


def test_validate_generated_names_skips_reserved_check_when_flag_false() -> None:
    """Names with check_reserved=False should only be checked for collisions."""
    names = [("string", "constant", False)]
    errors = validate_generated_names(names)
    assert not errors


def test_validate_generated_names_cross_collision_ignores_check_reserved_flag() -> None:
    """Cross-category collision detection applies regardless of check_reserved."""
    names = [
        ("status", "function from C symbol 'status'", True),
        ("status", "constant", False),
    ]
    errors = validate_generated_names(names)
    assert any("collides with" in e for e in errors)


def test_validate_generated_names_mixed_flags() -> None:
    """Only names with check_reserved=True should be checked against reserved sets."""
    names = [
        ("string", "constant", False),
        ("fmt", "function from C symbol 'fmt'", True),
    ]
    errors = validate_generated_names(names)
    # "string" should NOT produce an error (check_reserved=False).
    assert not any("string" in e for e in errors)
    # "fmt" should produce an import-name error (check_reserved=True).
    assert any("fmt" in e and "import name" in e for e in errors)
