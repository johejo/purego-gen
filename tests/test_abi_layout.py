# Copyright (c) 2026 purego-gen contributors.

"""Tests for ABI layout validation helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from purego_gen.abi_layout import (
    ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH,
    ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT,
    ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH,
    ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD,
    validate_record_layout,
)
from purego_gen.clang_parser import parse_declarations

if TYPE_CHECKING:
    from purego_gen.model import RecordTypedefDecl

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def _record_typedef_map() -> dict[str, RecordTypedefDecl]:
    declarations = parse_declarations(
        headers=(str(_FIXTURES_DIR / "sample_m3_types.h"),),
        clang_args=(),
    )
    return {record.name: record for record in declarations.record_typedefs}


def test_validate_record_layout_accepts_supported_structs() -> None:
    """Layout validation should pass on supported record typedefs from fixtures."""
    record_map = _record_typedef_map()

    for name in ("sample_point_t", "sample_point_alias_t", "sample_nested_point_t"):
        diagnostics = validate_record_layout(record_map[name])
        assert diagnostics == ()


def test_validate_record_layout_detects_offset_and_size_mismatch() -> None:
    """Layout utility should report deterministic mismatches for inconsistent metadata."""
    record_map = _record_typedef_map()
    sample_point = record_map["sample_point_t"]

    first_field = sample_point.fields[0]
    assert first_field.offset_bits is not None
    shifted_first_field = replace(first_field, offset_bits=first_field.offset_bits + 32)

    assert sample_point.size_bytes is not None
    mismatched_record = replace(
        sample_point,
        fields=(shifted_first_field, *sample_point.fields[1:]),
        size_bytes=sample_point.size_bytes + 8,
    )
    diagnostics = validate_record_layout(mismatched_record)
    diagnostic_codes = {diagnostic.code for diagnostic in diagnostics}

    assert ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH in diagnostic_codes
    assert ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH in diagnostic_codes


def test_validate_record_layout_reports_unsupported_record() -> None:
    """Unsupported record typedefs should return a stable unsupported diagnostic."""
    record_map = _record_typedef_map()
    sample_with_array = record_map["sample_with_array_t"]

    diagnostics = validate_record_layout(sample_with_array)

    assert len(diagnostics) == 1
    assert diagnostics[0].code == ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD
    assert "PG_TYPE_UNSUPPORTED_FIELD_TYPE" in diagnostics[0].message


def test_validate_record_layout_reports_missing_field_metadata() -> None:
    """Missing field layout metadata should be emitted as a dedicated diagnostic."""
    record_map = _record_typedef_map()
    sample_point = record_map["sample_point_t"]

    first_field = sample_point.fields[0]
    record_with_missing_offset = replace(
        sample_point,
        fields=(replace(first_field, offset_bits=None), *sample_point.fields[1:]),
    )
    diagnostics = validate_record_layout(record_with_missing_offset)
    diagnostic_codes = {diagnostic.code for diagnostic in diagnostics}

    assert ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT in diagnostic_codes
