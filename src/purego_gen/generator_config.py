# Copyright (c) 2026 purego-gen contributors.

"""Normalized generator configuration shared across invocation sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from purego_gen.config_model import GeneratorHelpers, HeaderOverlay
from purego_gen.model import TypeMappingOptions

if TYPE_CHECKING:
    from purego_gen.config_model import GeneratorSpec
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
    overlays: tuple[HeaderOverlay, ...] = ()
    helpers: GeneratorHelpers = field(default_factory=GeneratorHelpers)
    type_mapping: TypeMappingOptions = field(default_factory=TypeMappingOptions)


def build_generator_config(
    generator: GeneratorSpec,
    *,
    headers: tuple[str, ...],
    clang_args: tuple[str, ...] | None = None,
    overlays: tuple[HeaderOverlay, ...] | None = None,
) -> GeneratorConfig:
    """Build execution-ready config once header resolution is complete.

    Returns:
        Normalized generator config with resolved headers and clang args.
    """
    resolved_clang_args = generator.clang_args if clang_args is None else clang_args
    resolved_overlays = generator.overlays if overlays is None else overlays
    return GeneratorConfig(
        lib_id=generator.lib_id,
        headers=headers,
        package=generator.package,
        emit_kinds=generator.emit_kinds,
        func_filter=generator.filters.func,
        type_filter=generator.filters.type_,
        const_filter=generator.filters.const,
        var_filter=generator.filters.var,
        func_exclude_filter=generator.exclude_filters.func,
        type_exclude_filter=generator.exclude_filters.type_,
        const_exclude_filter=generator.exclude_filters.const,
        var_exclude_filter=generator.exclude_filters.var,
        clang_args=resolved_clang_args,
        overlays=resolved_overlays,
        helpers=generator.helpers,
        type_mapping=generator.type_mapping,
    )


__all__ = ["GeneratorConfig", "build_generator_config"]
