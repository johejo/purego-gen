# Copyright (c) 2026 purego-gen contributors.

"""Normalized declaration model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from purego_gen.diagnostic_codes import build_diagnostic_code

TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_ANONYMOUS_FIELD: Final[str] = build_diagnostic_code(
    "TYPE",
    "UNSUPPORTED",
    "ANONYMOUS",
    "FIELD",
)
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD: Final[str] = build_diagnostic_code(
    "TYPE",
    "UNSUPPORTED",
    "BITFIELD",
)
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE: Final[str] = build_diagnostic_code(
    "TYPE",
    "UNSUPPORTED",
    "FIELD",
    "TYPE",
)
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF: Final[str] = build_diagnostic_code(
    "TYPE",
    "UNSUPPORTED",
    "UNION",
    "TYPEDEF",
)
TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_RECORD_KIND: Final[str] = build_diagnostic_code(
    "TYPE",
    "UNSUPPORTED",
    "RECORD",
    "KIND",
)
TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS: Final[str] = build_diagnostic_code(
    "TYPE",
    "NO",
    "SUPPORTED",
    "FIELDS",
)
TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT: Final[str] = build_diagnostic_code(
    "TYPE",
    "OPAQUE",
    "INCOMPLETE",
    "STRUCT",
)


@dataclass(frozen=True, slots=True)
class FunctionDecl:
    """C function declaration model."""

    name: str
    result_c_type: str
    parameter_c_types: tuple[str, ...]
    parameter_names: tuple[str, ...]
    go_result_type: str | None
    go_parameter_types: tuple[str, ...]
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class TypeMappingOptions:
    """Type-mapping policy toggles for generated Go function signatures."""

    const_char_as_string: bool = False
    strict_enum_typedefs: bool = False
    typed_sentinel_constants: bool = False


@dataclass(frozen=True, slots=True)
class TypedefDecl:
    """Basic C typedef declaration model."""

    name: str
    c_type: str
    go_type: str
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class ConstantDecl:
    """Compile-time constant declaration model."""

    name: str
    value: int
    comment: str | None = None
    c_type: str | None = None
    go_expression: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeVarDecl:
    """Runtime data symbol declaration model."""

    name: str
    c_type: str
    comment: str | None = None


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
    is_incomplete: bool = False
    is_opaque: bool = False


@dataclass(frozen=True, slots=True)
class ParsedDeclarations:
    """All declarations parsed for one generation run."""

    functions: tuple[FunctionDecl, ...]
    typedefs: tuple[TypedefDecl, ...]
    constants: tuple[ConstantDecl, ...]
    runtime_vars: tuple[RuntimeVarDecl, ...]
    skipped_typedefs: tuple[SkippedTypedefDecl, ...] = ()
    record_typedefs: tuple[RecordTypedefDecl, ...] = ()
    opaque_pointer_typedef_names: frozenset[str] = frozenset()
