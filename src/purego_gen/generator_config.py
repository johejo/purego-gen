# Copyright (c) 2026 purego-gen contributors.

"""Normalized generator configuration shared across invocation sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from purego_gen.model import TypeMappingOptions

if TYPE_CHECKING:
    from purego_gen.declaration_filters import FilterSpec


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """One normalized purego-gen execution configuration."""

    lib_id: str
    headers: tuple[str, ...]
    package: str
    emit_kinds: tuple[str, ...]
    func_filter: FilterSpec | None = None
    type_filter: FilterSpec | None = None
    const_filter: FilterSpec | None = None
    var_filter: FilterSpec | None = None
    func_exclude_filter: FilterSpec | None = None
    type_exclude_filter: FilterSpec | None = None
    const_exclude_filter: FilterSpec | None = None
    var_exclude_filter: FilterSpec | None = None
    clang_args: tuple[str, ...] = ()
    type_mapping: TypeMappingOptions = field(default_factory=TypeMappingOptions)


__all__ = ["GeneratorConfig"]
