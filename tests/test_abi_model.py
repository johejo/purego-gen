# Copyright (c) 2026 purego-gen contributors.

"""Tests for structured ABI-model extraction from libclang declarations."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_parser import parse_declarations
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
    RecordTypedefDecl,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def _record_typedef_map() -> dict[str, RecordTypedefDecl]:
    header = _FIXTURES_DIR / "abi_types.h"
    declarations = parse_declarations(headers=(str(header),), clang_args=())
    return {record_typedef.name: record_typedef for record_typedef in declarations.record_typedefs}


def test_parse_record_typedef_model_lists_expected_records() -> None:
    """Parser should expose stable record typedef set for ABI checks."""
    record_typedef_map = _record_typedef_map()
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


def test_parse_record_typedef_model_supported_structs() -> None:
    """Supported struct typedefs should include stable field metadata."""
    record_typedef_map = _record_typedef_map()

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

    point_alias_record = record_typedef_map["fixture_point_alias_t"]
    assert point_alias_record.supported
    assert point_alias_record.size_bytes == point_record.size_bytes
    assert point_alias_record.align_bytes == point_record.align_bytes
    assert tuple(field.name for field in point_alias_record.fields) == (
        "left",
        "right",
        "mode",
        "label",
    )

    nested_record = record_typedef_map["fixture_nested_point_t"]
    assert nested_record.supported
    assert tuple(field.name for field in nested_record.fields) == ("point", "inner")
    assert all(field.supported for field in nested_record.fields)


def test_parse_record_typedef_model_unsupported_records() -> None:
    """Unsupported record patterns should expose deterministic diagnostics."""
    record_typedef_map = _record_typedef_map()

    array_record = record_typedef_map["fixture_with_array_t"]
    assert array_record.supported
    assert array_record.unsupported_code is None
    assert array_record.unsupported_reason is None
    assert len(array_record.fields) == 1
    assert array_record.fields[0].supported
    assert array_record.fields[0].unsupported_code is None

    union_record = record_typedef_map["fixture_union_t"]
    assert union_record.record_kind == "UNION_DECL"
    assert not union_record.supported
    assert union_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF
    assert union_record.unsupported_reason == "union typedefs are not supported in v1"

    bitfield_record = record_typedef_map["fixture_with_bitfield_t"]
    assert not bitfield_record.supported
    assert bitfield_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD
    assert bitfield_record.unsupported_reason == "bitfield flags is not supported in v1"
    assert len(bitfield_record.fields) == 1
    assert bitfield_record.fields[0].unsupported_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD
    assert not bitfield_record.fields[0].supported

    anonymous_record = record_typedef_map["fixture_with_anonymous_field_t"]
    assert not anonymous_record.supported
    assert anonymous_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS
    assert anonymous_record.unsupported_reason == "struct has no supported fields in v1"


def test_parse_record_typedef_model_opaque_handle() -> None:
    """Incomplete struct typedefs should be modeled as opaque handles."""
    record_typedef_map = _record_typedef_map()

    opaque_record = record_typedef_map["fixture_opaque_t"]
    assert not opaque_record.supported
    assert opaque_record.unsupported_code == TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT
    assert opaque_record.fields == ()
    assert opaque_record.is_incomplete
    assert opaque_record.is_opaque
