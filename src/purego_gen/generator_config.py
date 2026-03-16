# Copyright (c) 2026 purego-gen contributors.

"""Normalized generator configuration shared across invocation sources."""

from __future__ import annotations

from dataclasses import dataclass, field

from purego_gen.model import TypeMappingOptions


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """One normalized purego-gen execution configuration."""

    lib_id: str
    headers: tuple[str, ...]
    package: str
    emit_kinds: tuple[str, ...]
    func_filter: str | None = None
    type_filter: str | None = None
    const_filter: str | None = None
    var_filter: str | None = None
    clang_args: tuple[str, ...] = ()
    type_mapping: TypeMappingOptions = field(default_factory=TypeMappingOptions)


__all__ = ["GeneratorConfig"]
