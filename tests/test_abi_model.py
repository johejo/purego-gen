# Copyright (c) 2026 purego-gen contributors.

"""Tests for structured ABI-model extraction from libclang declarations."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_parser import parse_declarations
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def test_parse_record_typedef_model_for_pre_m4_abi() -> None:
    """Parser should expose structured record/field metadata for ABI checks."""
    header = _FIXTURES_DIR / "abi_types.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    record_typedef_map = {
        record_typedef.name: record_typedef for record_typedef in declarations.record_typedefs
    }
    assert tuple(record_typedef_map) == (
        "fixture_point_t",
        "fixture_point_alias_t",
        "fixture_nested_point_t",
        "fixture_with_array_t",
        "fixture_union_t",
        "fixture_with_bitfield_t",
        "fixture_with_anonymous_field_t",
        "fixture_opaque_t",
    )

    point_record = record_typedef_map["fixture_point_t"]
    assert point_record.supported
    assert point_record.unsupported_code is None
    assert point_record.unsupported_reason is None
    assert point_record.size_bytes is not None
    assert point_record.size_bytes > 0
    assert point_record.align_bytes is not None
    assert point_record.align_bytes > 0
    assert tuple(field.name for field in point_record.fields) == (
        "left",
        "right",
        "mode",
        "label",
    )
    assert point_record.fields[0].offset_bits == 0
    assert all(field.offset_bits is not None for field in point_record.fields)
    assert all(field.supported for field in point_record.fields)

    array_record = record_typedef_map["fixture_with_array_t"]
    assert not array_record.supported
    assert array_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE
    assert array_record.unsupported_reason is not None
    assert "unsupported field type for values:" in array_record.unsupported_reason
    assert len(array_record.fields) == 1
    assert array_record.fields[0].unsupported_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE
    assert not array_record.fields[0].supported

    union_record = record_typedef_map["fixture_union_t"]
    assert union_record.record_kind == "UNION_DECL"
    assert not union_record.supported
    assert union_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF
    assert union_record.unsupported_reason == "union typedefs are not supported in v1"

    opaque_record = record_typedef_map["fixture_opaque_t"]
    assert not opaque_record.supported
    assert opaque_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS
    assert opaque_record.fields == ()
