# Copyright (c) 2026 purego-gen contributors.

"""Tests for structured ABI-model extraction from libclang declarations."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_parser import parse_declarations

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def test_parse_record_typedef_model_for_pre_m4_abi() -> None:
    """Parser should expose structured record/field metadata for ABI checks."""
    header = _FIXTURES_DIR / "sample_m3_types.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    record_typedef_map = {
        record_typedef.name: record_typedef for record_typedef in declarations.record_typedefs
    }
    assert tuple(record_typedef_map) == (
        "sample_point_t",
        "sample_point_alias_t",
        "sample_nested_point_t",
        "sample_with_array_t",
        "sample_union_t",
        "sample_with_bitfield_t",
        "sample_with_anonymous_field_t",
        "sample_opaque_t",
    )

    sample_point = record_typedef_map["sample_point_t"]
    assert sample_point.supported
    assert sample_point.unsupported_reason is None
    assert sample_point.size_bytes is not None
    assert sample_point.size_bytes > 0
    assert sample_point.align_bytes is not None
    assert sample_point.align_bytes > 0
    assert tuple(field.name for field in sample_point.fields) == (
        "left",
        "right",
        "mode",
        "label",
    )
    assert sample_point.fields[0].offset_bits == 0
    assert all(field.offset_bits is not None for field in sample_point.fields)
    assert all(field.supported for field in sample_point.fields)

    sample_with_array = record_typedef_map["sample_with_array_t"]
    assert not sample_with_array.supported
    assert sample_with_array.unsupported_reason is not None
    assert "unsupported field type for values:" in sample_with_array.unsupported_reason
    assert len(sample_with_array.fields) == 1
    assert not sample_with_array.fields[0].supported

    sample_union = record_typedef_map["sample_union_t"]
    assert sample_union.record_kind == "UNION_DECL"
    assert not sample_union.supported
    assert sample_union.unsupported_reason == "union typedefs are not supported in v1"

    sample_opaque = record_typedef_map["sample_opaque_t"]
    assert not sample_opaque.supported
    assert sample_opaque.fields == ()
