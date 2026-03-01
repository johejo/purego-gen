# Copyright (c) 2026 purego-gen contributors.

"""Unit tests for CLI option parsing."""

from __future__ import annotations

from purego_gen.cli import parse_options
from purego_gen.model import TypeMappingOptions


def test_parse_options_keeps_existing_type_mapping_defaults() -> None:
    """Existing type-mapping behavior should stay unchanged without new flags."""
    options = parse_options([
        "--lib-id",
        "fixture_lib",
        "--header",
        "fixture.h",
        "--const-char-as-string",
    ])
    assert options.type_mapping == TypeMappingOptions(
        const_char_as_string=True,
        strict_enum_typedefs=False,
        typed_sentinel_constants=False,
    )


def test_parse_options_enables_new_strict_typing_flags() -> None:
    """New strict typing flags should map to type-mapping options."""
    options = parse_options([
        "--lib-id",
        "fixture_lib",
        "--header",
        "fixture.h",
        "--strict-enum-typedefs",
        "--typed-sentinel-constants",
    ])
    assert options.type_mapping == TypeMappingOptions(
        strict_enum_typedefs=True,
        typed_sentinel_constants=True,
    )
