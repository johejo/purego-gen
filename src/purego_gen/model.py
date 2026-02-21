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
class ParsedDeclarations:
    """All declarations parsed for one generation run."""

    functions: tuple[FunctionDecl, ...]
    typedefs: tuple[TypedefDecl, ...]
