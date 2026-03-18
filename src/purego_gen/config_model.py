# Copyright (c) 2026 purego-gen contributors.

"""Resolved shared config models for generator execution."""

from dataclasses import dataclass
from pathlib import Path

from purego_gen.declaration_filters import FilterSpec
from purego_gen.model import TypeMappingOptions

PathType = Path
TypeMappingOptionsType = TypeMappingOptions
FilterSpecType = FilterSpec


@dataclass(frozen=True, slots=True)
class GeneratorFilters:
    """Optional per-category declaration filters."""

    func: FilterSpecType | None = None
    type_: FilterSpecType | None = None
    const: FilterSpecType | None = None
    var: FilterSpecType | None = None


@dataclass(frozen=True, slots=True)
class BufferInputPair:
    """One pointer/length parameter pair rewritten by a generated helper."""

    pointer: str
    length: str


@dataclass(frozen=True, slots=True)
class BufferInputHelper:
    """One function-specific helper definition for `[]byte` inputs."""

    function: str
    pairs: tuple[BufferInputPair, ...]


@dataclass(frozen=True, slots=True)
class GeneratorHelpers:
    """Optional helper-generation configuration."""

    buffer_inputs: tuple[BufferInputHelper, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalHeaders:
    """Header source definition for local file paths."""

    headers: tuple[PathType, ...]


@dataclass(frozen=True, slots=True)
class EnvIncludeHeaders:
    """Header source definition via include-directory environment variable."""

    include_dir_env: str
    headers: tuple[str, ...]


HeaderConfig = LocalHeaders | EnvIncludeHeaders


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    """Resolved generator configuration prior to env-backed header expansion."""

    lib_id: str
    package: str
    emit_kinds: tuple[str, ...]
    headers: HeaderConfig
    filters: GeneratorFilters
    exclude_filters: GeneratorFilters
    helpers: GeneratorHelpers
    type_mapping: TypeMappingOptionsType
    clang_args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Shared generator config loaded from disk."""

    config_path: PathType
    generator: GeneratorSpec


__all__ = [
    "AppConfig",
    "BufferInputHelper",
    "BufferInputPair",
    "EnvIncludeHeaders",
    "GeneratorFilters",
    "GeneratorHelpers",
    "GeneratorSpec",
    "HeaderConfig",
    "LocalHeaders",
]
