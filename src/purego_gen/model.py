# Copyright (c) 2026 purego-gen contributors.

"""Normalized declaration model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FunctionDecl:
    """C function declaration model."""

    name: str
    result_c_type: str
    parameter_c_types: tuple[str, ...]


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


@dataclass(frozen=True, slots=True)
class SkippedTypedefDecl:
    """Typedef skipped because current mapping rules do not support it."""

    name: str
    c_type: str
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
