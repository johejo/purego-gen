# Copyright (c) 2026 purego-gen contributors.

"""ABI layout validation utilities for record typedef metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from purego_gen.diagnostic_codes import build_diagnostic_code

if TYPE_CHECKING:
    from purego_gen.model import RecordFieldDecl, RecordTypedefDecl

ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "UNSUPPORTED",
    "RECORD",
)
ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "UNSUPPORTED",
    "FIELD",
)
ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_RECORD_LAYOUT: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "MISSING",
    "RECORD",
    "LAYOUT",
)
ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "MISSING",
    "FIELD",
    "LAYOUT",
)
ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_NOT_BYTE_ALIGNED: Final[str] = (
    build_diagnostic_code(
        "ABI",
        "LAYOUT",
        "FIELD",
        "OFFSET",
        "NOT",
        "BYTE",
        "ALIGNED",
    )
)
ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "FIELD",
    "OFFSET",
    "MISMATCH",
)
ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_ALIGN_MISMATCH: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "RECORD",
    "ALIGN",
    "MISMATCH",
)
ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH: Final[str] = build_diagnostic_code(
    "ABI",
    "LAYOUT",
    "RECORD",
    "SIZE",
    "MISMATCH",
)
ABI_LAYOUT_RESULT_STATUS_PASSED: Final[str] = "passed"
ABI_LAYOUT_RESULT_STATUS_FAILED: Final[str] = "failed"
ABI_LAYOUT_RESULT_STATUS_SKIPPED: Final[str] = "skipped"
ABI_LAYOUT_FALLBACK_REASON_UNSUPPORTED_PATTERN: Final[str] = "unsupported_pattern"
ABI_LAYOUT_FALLBACK_REASON_INCOMPLETE_METADATA: Final[str] = "incomplete_metadata"


@dataclass(frozen=True, slots=True)
class AbiLayoutDiagnostic:
    """Layout-validation diagnostic for one record typedef."""

    code: str
    message: str
    source_code: str | None = None


@dataclass(frozen=True, slots=True)
class AbiLayoutValidationResult:
    """Record-level ABI layout validation outcome."""

    record_name: str
    status: str
    fallback_reason: str | None
    diagnostics: tuple[AbiLayoutDiagnostic, ...]


def _align_up(value: int, alignment: int) -> int:
    """Round `value` up to the nearest alignment boundary.

    Returns:
        Aligned value.
    """
    return ((value + alignment - 1) // alignment) * alignment


def _validate_field_layout(
    field: RecordFieldDecl,
    *,
    record_name: str,
    current_offset_bytes: int,
) -> tuple[tuple[AbiLayoutDiagnostic, ...], int]:
    """Validate one field's layout metadata and expected byte offset.

    Returns:
        Tuple of emitted diagnostics and next expected field offset in bytes.
    """
    if not field.supported:
        reason = field.unsupported_reason or "unsupported field"
        details = f"{field.unsupported_code}: " if field.unsupported_code is not None else ""
        return (
            (
                AbiLayoutDiagnostic(
                    code=ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD,
                    message=f"{record_name}.{field.name}: {details}{reason}",
                    source_code=field.unsupported_code,
                ),
            ),
            current_offset_bytes,
        )
    if field.offset_bits is None or field.size_bytes is None or field.align_bytes is None:
        return (
            (
                AbiLayoutDiagnostic(
                    code=ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT,
                    message=(
                        f"{record_name}.{field.name}: missing field layout metadata "
                        "(offset_bits/size_bytes/align_bytes)"
                    ),
                ),
            ),
            current_offset_bytes,
        )
    if field.align_bytes <= 0:
        return (
            (
                AbiLayoutDiagnostic(
                    code=ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT,
                    message=f"{record_name}.{field.name}: align_bytes must be positive",
                ),
            ),
            current_offset_bytes,
        )
    if field.offset_bits % 8 != 0:
        return (
            (
                AbiLayoutDiagnostic(
                    code=ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_NOT_BYTE_ALIGNED,
                    message=(
                        f"{record_name}.{field.name}: offset_bits must be byte-aligned, "
                        f"got {field.offset_bits}"
                    ),
                ),
            ),
            current_offset_bytes,
        )

    expected_offset_bytes = _align_up(current_offset_bytes, field.align_bytes)
    actual_offset_bytes = field.offset_bits // 8
    diagnostics: tuple[AbiLayoutDiagnostic, ...] = ()
    if actual_offset_bytes != expected_offset_bytes:
        diagnostics = (
            AbiLayoutDiagnostic(
                code=ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH,
                message=(
                    f"{record_name}.{field.name}: expected byte offset {expected_offset_bytes}, "
                    f"got {actual_offset_bytes}"
                ),
            ),
        )
    next_offset_bytes = expected_offset_bytes + field.size_bytes
    return diagnostics, next_offset_bytes


def _is_field_usable_for_record_layout(field: RecordFieldDecl) -> bool:
    """Check whether a field has complete byte-addressable layout metadata.

    Returns:
        `True` when layout finalization can include this field.
    """
    return (
        field.supported
        and field.offset_bits is not None
        and field.size_bytes is not None
        and field.align_bytes is not None
        and field.align_bytes > 0
        and field.offset_bits % 8 == 0
    )


def validate_record_layout(record: RecordTypedefDecl) -> tuple[AbiLayoutDiagnostic, ...]:
    """Validate record layout metadata using clang-provided sizes/alignments.

    For supported records, this utility recomputes expected field offsets, struct
    alignment, and final struct size from field-level size/alignment metadata and
    compares the result with clang-reported layout values.

    Returns:
        Layout diagnostics. Empty tuple means no mismatches were found.
    """
    if not record.supported:
        reason = record.unsupported_reason or "unsupported record typedef"
        details = f"{record.unsupported_code}: " if record.unsupported_code is not None else ""
        return (
            AbiLayoutDiagnostic(
                code=ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD,
                message=f"{record.name}: {details}{reason}",
                source_code=record.unsupported_code,
            ),
        )

    if record.size_bytes is None or record.align_bytes is None:
        return (
            AbiLayoutDiagnostic(
                code=ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_RECORD_LAYOUT,
                message=f"{record.name}: missing record size_bytes/align_bytes metadata",
            ),
        )

    diagnostics: list[AbiLayoutDiagnostic] = []
    current_offset_bytes = 0
    max_field_align = 1
    can_finalize_record_layout = True

    for field in record.fields:
        field_diagnostics, next_offset_bytes = _validate_field_layout(
            field,
            record_name=record.name,
            current_offset_bytes=current_offset_bytes,
        )
        if field_diagnostics:
            diagnostics.extend(field_diagnostics)
        if not _is_field_usable_for_record_layout(field):
            can_finalize_record_layout = False
            continue
        if field.align_bytes is None:
            can_finalize_record_layout = False
            continue
        max_field_align = max(max_field_align, field.align_bytes)
        current_offset_bytes = next_offset_bytes

    if not can_finalize_record_layout:
        return tuple(diagnostics)

    expected_record_align = max_field_align
    if record.align_bytes != expected_record_align:
        diagnostics.append(
            AbiLayoutDiagnostic(
                code=ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_ALIGN_MISMATCH,
                message=(
                    f"{record.name}: expected align_bytes {expected_record_align}, "
                    f"got {record.align_bytes}"
                ),
            )
        )

    expected_record_size = _align_up(current_offset_bytes, expected_record_align)
    if record.size_bytes != expected_record_size:
        diagnostics.append(
            AbiLayoutDiagnostic(
                code=ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH,
                message=(
                    f"{record.name}: expected size_bytes {expected_record_size}, "
                    f"got {record.size_bytes}"
                ),
            )
        )

    return tuple(diagnostics)


def _has_layout_mismatch_diagnostics(diagnostics: tuple[AbiLayoutDiagnostic, ...]) -> bool:
    """Check whether diagnostics contain deterministic layout mismatches.

    Returns:
        `True` when offset/align/size mismatch diagnostics are present.
    """
    mismatch_codes = {
        ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_MISMATCH,
        ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_ALIGN_MISMATCH,
        ABI_LAYOUT_DIAGNOSTIC_CODE_RECORD_SIZE_MISMATCH,
    }
    return any(diagnostic.code in mismatch_codes for diagnostic in diagnostics)


def _is_unsupported_pattern_diagnostic(diagnostic: AbiLayoutDiagnostic) -> bool:
    """Check whether one diagnostic indicates unsupported ABI-sensitive pattern.

    Returns:
        `True` when diagnostic corresponds to unsupported record/field patterns.
    """
    return diagnostic.code in {
        ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD,
        ABI_LAYOUT_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD,
    }


def _is_incomplete_metadata_diagnostic(diagnostic: AbiLayoutDiagnostic) -> bool:
    """Check whether one diagnostic indicates incomplete layout metadata.

    Returns:
        `True` when diagnostic indicates metadata is insufficient for full validation.
    """
    return diagnostic.code in {
        ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_RECORD_LAYOUT,
        ABI_LAYOUT_DIAGNOSTIC_CODE_MISSING_FIELD_LAYOUT,
        ABI_LAYOUT_DIAGNOSTIC_CODE_FIELD_OFFSET_NOT_BYTE_ALIGNED,
    }


def validate_record_layout_with_fallback(record: RecordTypedefDecl) -> AbiLayoutValidationResult:
    """Validate one record layout with explicit fallback classification.

    Returns:
        Validation result with one of `passed`/`failed`/`skipped`.
    """
    diagnostics = validate_record_layout(record)
    if not diagnostics:
        return AbiLayoutValidationResult(
            record_name=record.name,
            status=ABI_LAYOUT_RESULT_STATUS_PASSED,
            fallback_reason=None,
            diagnostics=(),
        )

    if any(_is_unsupported_pattern_diagnostic(diagnostic) for diagnostic in diagnostics):
        return AbiLayoutValidationResult(
            record_name=record.name,
            status=ABI_LAYOUT_RESULT_STATUS_SKIPPED,
            fallback_reason=ABI_LAYOUT_FALLBACK_REASON_UNSUPPORTED_PATTERN,
            diagnostics=diagnostics,
        )

    if any(_is_incomplete_metadata_diagnostic(diagnostic) for diagnostic in diagnostics):
        return AbiLayoutValidationResult(
            record_name=record.name,
            status=ABI_LAYOUT_RESULT_STATUS_SKIPPED,
            fallback_reason=ABI_LAYOUT_FALLBACK_REASON_INCOMPLETE_METADATA,
            diagnostics=diagnostics,
        )

    if _has_layout_mismatch_diagnostics(diagnostics):
        return AbiLayoutValidationResult(
            record_name=record.name,
            status=ABI_LAYOUT_RESULT_STATUS_FAILED,
            fallback_reason=None,
            diagnostics=diagnostics,
        )

    return AbiLayoutValidationResult(
        record_name=record.name,
        status=ABI_LAYOUT_RESULT_STATUS_SKIPPED,
        fallback_reason=ABI_LAYOUT_FALLBACK_REASON_INCOMPLETE_METADATA,
        diagnostics=diagnostics,
    )
