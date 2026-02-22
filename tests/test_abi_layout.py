# Copyright (c) 2026 purego-gen contributors.

"""Tests for ABI layout validation helpers."""

from __future__ import annotations

import subprocess  # noqa: S404
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from purego_gen.abi_layout import (
    ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH,
    ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT,
    ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH,
    ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD,
    ABI_LAYOUT_FALLBACK_REASON_INCOMPLETE_METADATA,
    ABI_LAYOUT_FALLBACK_REASON_UNSUPPORTED_PATTERN,
    ABI_LAYOUT_RESULT_STATUS_FAILED,
    ABI_LAYOUT_RESULT_STATUS_PASSED,
    ABI_LAYOUT_RESULT_STATUS_SKIPPED,
    validate_record_layout,
    validate_record_layout_with_fallback,
)
from purego_gen.clang_parser import parse_declarations
from purego_gen.toolchain import resolve_c_compiler_command

if TYPE_CHECKING:
    from purego_gen.model import RecordTypedefDecl

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_ABI_PROBE_SOURCE = _FIXTURES_DIR / "abi_probe_sample_m3_types.c"
_PROBE_RECORD_PARTS = 4
_PROBE_FIELD_PARTS = 6


@dataclass(slots=True)
class _ProbeFieldLayout:
    """One field layout entry captured from the C-side probe."""

    offset_bits: int
    size_bytes: int
    align_bytes: int


@dataclass(slots=True)
class _ProbeRecordLayout:
    """One record layout entry captured from the C-side probe."""

    size_bytes: int
    align_bytes: int
    fields: dict[str, _ProbeFieldLayout]


def _record_typedef_map() -> dict[str, RecordTypedefDecl]:
    declarations = parse_declarations(
        headers=(str(_FIXTURES_DIR / "sample_m3_types.h"),),
        clang_args=(),
    )
    return {record.name: record for record in declarations.record_typedefs}


def _build_probe_compile_command(probe_binary_path: Path) -> list[str]:
    """Build compile command for the ABI probe source.

    Returns:
        Compiler command with arguments.
    """
    command = resolve_c_compiler_command(purpose="ABI probe tests")
    command.extend([
        "-std=gnu11",
        "-I",
        str(_FIXTURES_DIR),
        str(_ABI_PROBE_SOURCE),
        "-o",
        str(probe_binary_path),
    ])
    return command


def _parse_probe_layout_output(output: str) -> dict[str, _ProbeRecordLayout]:
    """Parse ABI probe output lines into structured layout mappings.

    Returns:
        Record layout mapping keyed by typedef name.

    Raises:
        AssertionError: Probe output line is malformed.
    """
    records: dict[str, _ProbeRecordLayout] = {}
    for line in output.splitlines():
        parts = line.split(",")
        if not parts:
            continue
        if parts[0] == "record":
            assert len(parts) == _PROBE_RECORD_PARTS, f"invalid record probe line: {line}"
            _, record_name, size_bytes, align_bytes = parts
            records[record_name] = _ProbeRecordLayout(
                size_bytes=int(size_bytes),
                align_bytes=int(align_bytes),
                fields={},
            )
            continue
        if parts[0] == "field":
            assert len(parts) == _PROBE_FIELD_PARTS, f"invalid field probe line: {line}"
            _, record_name, field_name, offset_bits, size_bytes, align_bytes = parts
            record = records.get(record_name)
            assert record is not None, f"field probe emitted before record: {line}"
            record.fields[field_name] = _ProbeFieldLayout(
                offset_bits=int(offset_bits),
                size_bytes=int(size_bytes),
                align_bytes=int(align_bytes),
            )
            continue
        message = f"invalid ABI probe tag in line: {line}"
        raise AssertionError(message)
    return records


def _run_c_layout_probe(tmp_path: Path) -> dict[str, _ProbeRecordLayout]:
    """Compile and run C-side ABI probe.

    Returns:
        Parsed record layout mapping from probe output.
    """
    probe_binary_path = tmp_path / "abi_probe_sample_m3_types"
    compile_result = subprocess.run(  # noqa: S603
        _build_probe_compile_command(probe_binary_path),
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        text=True,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    run_result = subprocess.run(  # noqa: S603
        [str(probe_binary_path)],
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        text=True,
    )
    assert run_result.returncode == 0, run_result.stderr
    return _parse_probe_layout_output(run_result.stdout)


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
    assert diagnostics[0].source_code == "PG_TYPE_UNSUPPORTED_FIELD_TYPE"
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


def test_record_layout_matches_c_probe_fixture(tmp_path: Path) -> None:
    """Parsed layout metadata should match C-side probe for supported fixtures."""
    record_map = _record_typedef_map()
    c_layouts = _run_c_layout_probe(tmp_path)

    assert tuple(c_layouts) == (
        "sample_point_t",
        "sample_point_alias_t",
        "sample_nested_point_t",
    )
    for record_name, c_record in c_layouts.items():
        parsed_record = record_map[record_name]
        assert parsed_record.supported
        assert parsed_record.size_bytes == c_record.size_bytes
        assert parsed_record.align_bytes == c_record.align_bytes

        parsed_fields = {field.name: field for field in parsed_record.fields}
        assert tuple(parsed_fields) == tuple(c_record.fields)
        for field_name, c_field in c_record.fields.items():
            parsed_field = parsed_fields[field_name]
            assert parsed_field.supported
            assert parsed_field.offset_bits == c_field.offset_bits
            assert parsed_field.size_bytes == c_field.size_bytes
            assert parsed_field.align_bytes == c_field.align_bytes


def test_validate_record_layout_with_fallback_reports_skipped_for_unsupported_pattern() -> None:
    """Fallback result should mark unsupported ABI patterns as skipped."""
    record_map = _record_typedef_map()
    result = validate_record_layout_with_fallback(record_map["sample_with_array_t"])

    assert result.record_name == "sample_with_array_t"
    assert result.status == ABI_LAYOUT_RESULT_STATUS_SKIPPED
    assert result.fallback_reason == ABI_LAYOUT_FALLBACK_REASON_UNSUPPORTED_PATTERN
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].source_code == "PG_TYPE_UNSUPPORTED_FIELD_TYPE"


def test_validate_record_layout_with_fallback_reports_skipped_for_incomplete_metadata() -> None:
    """Fallback result should mark incomplete layout metadata as skipped."""
    record_map = _record_typedef_map()
    sample_point = record_map["sample_point_t"]
    first_field = sample_point.fields[0]
    incomplete_record = replace(
        sample_point,
        fields=(replace(first_field, offset_bits=None), *sample_point.fields[1:]),
    )

    result = validate_record_layout_with_fallback(incomplete_record)

    assert result.status == ABI_LAYOUT_RESULT_STATUS_SKIPPED
    assert result.fallback_reason == ABI_LAYOUT_FALLBACK_REASON_INCOMPLETE_METADATA
    assert any(
        diagnostic.code == ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT
        for diagnostic in result.diagnostics
    )


def test_validate_record_layout_with_fallback_reports_failed_on_layout_mismatch() -> None:
    """Fallback result should mark deterministic offset/size mismatches as failed."""
    record_map = _record_typedef_map()
    sample_point = record_map["sample_point_t"]
    first_field = sample_point.fields[0]
    assert first_field.offset_bits is not None
    assert sample_point.size_bytes is not None
    mismatched_record = replace(
        sample_point,
        fields=(
            replace(first_field, offset_bits=first_field.offset_bits + 32),
            *sample_point.fields[1:],
        ),
        size_bytes=sample_point.size_bytes + 8,
    )

    result = validate_record_layout_with_fallback(mismatched_record)

    assert result.status == ABI_LAYOUT_RESULT_STATUS_FAILED
    assert result.fallback_reason is None
    assert any(
        diagnostic.code == ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH
        for diagnostic in result.diagnostics
    )
    assert any(
        diagnostic.code == ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH
        for diagnostic in result.diagnostics
    )


def test_validate_record_layout_with_fallback_reports_passed_when_clean() -> None:
    """Fallback result should mark clean supported records as passed."""
    record_map = _record_typedef_map()
    result = validate_record_layout_with_fallback(record_map["sample_point_t"])

    assert result.status == ABI_LAYOUT_RESULT_STATUS_PASSED
    assert result.fallback_reason is None
    assert result.diagnostics == ()
