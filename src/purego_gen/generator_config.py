# Copyright (c) 2026 purego-gen contributors.

"""Normalized generator configuration shared across invocation sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from purego_gen.config_model import GeneratorFilters, GeneratorRenderSpec, HeaderOverlay

if TYPE_CHECKING:
    from purego_gen.config_model import GeneratorSpec
    from purego_gen.declaration_filters import FilterSpec


@dataclass(frozen=True, slots=True)
class ResolvedGeneratorParseConfig:
    """Execution-ready parse configuration with resolved headers."""

    headers: tuple[str, ...]
    clang_args: tuple[str, ...] = ()
    overlays: tuple[HeaderOverlay, ...] = ()
    filters: GeneratorFilters = field(default_factory=GeneratorFilters)
    exclude_filters: GeneratorFilters = field(default_factory=GeneratorFilters)

    @property
    def func_filter(self) -> FilterSpec | None:
        """Return the resolved function include filter."""
        return self.filters.func

    @property
    def type_filter(self) -> FilterSpec | None:
        """Return the resolved typedef include filter."""
        return self.filters.type_

    @property
    def const_filter(self) -> FilterSpec | None:
        """Return the resolved constant include filter."""
        return self.filters.const

    @property
    def var_filter(self) -> FilterSpec | None:
        """Return the resolved runtime-variable include filter."""
        return self.filters.var

    @property
    def func_exclude_filter(self) -> FilterSpec | None:
        """Return the resolved function exclude filter."""
        return self.exclude_filters.func

    @property
    def type_exclude_filter(self) -> FilterSpec | None:
        """Return the resolved typedef exclude filter."""
        return self.exclude_filters.type_

    @property
    def const_exclude_filter(self) -> FilterSpec | None:
        """Return the resolved constant exclude filter."""
        return self.exclude_filters.const

    @property
    def var_exclude_filter(self) -> FilterSpec | None:
        """Return the resolved runtime-variable exclude filter."""
        return self.exclude_filters.var


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """One normalized purego-gen execution configuration."""

    lib_id: str
    package: str
    emit_kinds: tuple[str, ...]
    parse: ResolvedGeneratorParseConfig
    render: GeneratorRenderSpec = field(default_factory=GeneratorRenderSpec)


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
    resolved_clang_args = generator.parse.clang_args if clang_args is None else clang_args
    resolved_overlays = generator.parse.overlays if overlays is None else overlays
    return GeneratorConfig(
        lib_id=generator.lib_id,
        package=generator.package,
        emit_kinds=generator.emit_kinds,
        parse=ResolvedGeneratorParseConfig(
            headers=headers,
            clang_args=resolved_clang_args,
            overlays=resolved_overlays,
            filters=generator.parse.filters,
            exclude_filters=generator.parse.exclude_filters,
        ),
        render=generator.render,
    )


__all__ = ["GeneratorConfig", "ResolvedGeneratorParseConfig", "build_generator_config"]
