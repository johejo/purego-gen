# Copyright (c) 2026 purego-gen contributors.

"""Normalized declaration model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_ANONYMOUS_FIELD: Final[str] = "PG_TYPE_UNSUPPORTED_ANONYMOUS_FIELD"
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD: Final[str] = "PG_TYPE_UNSUPPORTED_BITFIELD"
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE: Final[str] = "PG_TYPE_UNSUPPORTED_FIELD_TYPE"
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF: Final[str] = "PG_TYPE_UNSUPPORTED_UNION_TYPEDEF"
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD_KIND: Final[str] = "PG_TYPE_UNSUPPORTED_RECORD_KIND"
TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS: Final[str] = "PG_TYPE_NO_SUPPORTED_FIELDS"


@dataclass(frozen=True, slots=True)
class FunctionDecl:
    """C function declaration model."""

    name: str
    result_c_type: str
    parameter_c_types: tuple[str, ...]
    go_result_type: str | None
    go_parameter_types: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True, slots=True)
class TypedefDecl:
    """Basic C typedef declaration model."""

    name: str
    c_type: str
    go_type: str


@dataclass(frozen=True, slots=True)
class ConstantDecl:
    """Compile-time constant declaration model."""

    name: str
    value: int


@dataclass(frozen=True, slots=True)
class RuntimeVarDecl:
    """Runtime data symbol declaration model."""

    name: str
    c_type: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class SkippedTypedefDecl:
    """Typedef skipped because current mapping rules do not support it."""

    name: str
    c_type: str
    reason_code: str
    reason: str


@dataclass(frozen=True, slots=True)
class RecordFieldDecl:
    """Structured field metadata for a C record declaration."""

    name: str
    c_type: str
    kind: str
    offset_bits: int | None
    size_bytes: int | None
    align_bytes: int | None
    is_bitfield: bool
    bitfield_width: int | None
    supported: bool
    unsupported_code: str | None
    unsupported_reason: str | None


@dataclass(frozen=True, slots=True)
class RecordTypedefDecl:
    """Structured record typedef metadata used by ABI validation."""

    name: str
    c_type: str
    record_kind: str
    size_bytes: int | None
    align_bytes: int | None
    fields: tuple[RecordFieldDecl, ...]
    supported: bool
    unsupported_code: str | None
    unsupported_reason: str | None


@dataclass(frozen=True, slots=True)
class ParsedDeclarations:
    """All declarations parsed for one generation run."""

    functions: tuple[FunctionDecl, ...]
    typedefs: tuple[TypedefDecl, ...]
    constants: tuple[ConstantDecl, ...]
    runtime_vars: tuple[RuntimeVarDecl, ...]
    skipped_typedefs: tuple[SkippedTypedefDecl, ...] = ()
    record_typedefs: tuple[RecordTypedefDecl, ...] = ()
