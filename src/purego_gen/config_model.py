# Copyright (c) 2026 purego-gen contributors.

"""Resolved shared config models for generator execution."""

from dataclasses import dataclass, field
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
class HeaderOverlay:
    """One in-memory header overlay provided to libclang."""

    path: str
    content: str


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
class CallbackInputHelper:
    """One function-specific helper definition for callback parameters."""

    function: str
    parameters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OwnedStringReturnHelper:
    """One function-specific helper definition for owned ``const char *`` returns."""

    function: str
    free_func: str


@dataclass(frozen=True, slots=True)
class GeneratorHelpers:
    """Optional helper-generation configuration."""

    buffer_inputs: tuple[BufferInputHelper, ...] = ()
    callback_inputs: tuple[CallbackInputHelper, ...] = ()
    owned_string_returns: tuple[OwnedStringReturnHelper, ...] = ()


@dataclass(frozen=True, slots=True)
class GeneratorNaming:
    """Generated Go identifier naming policy."""

    type_prefix: str = "purego_"
    const_prefix: str = "purego_"
    func_prefix: str = "purego_"
    var_prefix: str = "purego_"

    def type_name(self, identifier: str) -> str:
        """Build one generated typedef alias name.

        Returns:
            Generated typedef alias identifier.
        """
        return f"{self.type_prefix}type_{identifier}"

    def const_name(self, identifier: str) -> str:
        """Build one generated constant name.

        Returns:
            Generated constant identifier.
        """
        return f"{self.const_prefix}const_{identifier}" if self.const_prefix else identifier

    def func_name(self, identifier: str) -> str:
        """Build one generated function variable or helper name.

        Returns:
            Generated function-related identifier.
        """
        return f"{self.func_prefix}func_{identifier}"

    def runtime_var_name(self, identifier: str) -> str:
        """Build one generated runtime variable name.

        Returns:
            Generated runtime-variable identifier.
        """
        return f"{self.var_prefix}var_{identifier}"

    def func_type_name(self, identifier: str) -> str:
        """Build one generated func-type alias name for a function-pointer typedef.

        Returns:
            Generated func-type alias identifier.
        """
        return f"{self.type_prefix}type_{identifier}_func"

    def newcallback_name(self, identifier: str) -> str:
        """Build one generated NewCallback helper name for a function-pointer typedef.

        Returns:
            Generated NewCallback helper identifier.
        """
        return f"{self.func_prefix}new_{identifier}"

    def callback_func_type_name(self, param_name: str) -> str:
        """Build one generated func-type alias name for a callback parameter.

        Returns:
            Generated func-type alias identifier.
        """
        return f"{self.type_prefix}type_{param_name}_func"

    def callback_func_type_name_qualified(self, function_name: str, param_name: str) -> str:
        """Build one qualified func-type alias name for an ambiguous callback parameter.

        Returns:
            Generated func-type alias identifier qualified by function name.
        """
        return f"{self.type_prefix}type_{function_name}_{param_name}_func"

    def callback_newcallback_name(self, param_name: str) -> str:
        """Build one generated NewCallback helper name for a callback parameter.

        Returns:
            Generated NewCallback helper identifier.
        """
        return f"{self.func_prefix}new_{param_name}"

    def callback_newcallback_name_qualified(self, function_name: str, param_name: str) -> str:
        """Build one qualified NewCallback helper name for an ambiguous callback parameter.

        Returns:
            Generated NewCallback helper identifier qualified by function name.
        """
        return f"{self.func_prefix}new_{function_name}_{param_name}"

    def register_functions_name(self, lib_id: str) -> str:
        """Build the generated function-registration helper name.

        Returns:
            Generated register-functions helper identifier.
        """
        return f"{self.func_prefix}{lib_id}_register_functions"

    def load_runtime_vars_name(self, lib_id: str) -> str:
        """Build the generated runtime-variable loader helper name.

        Returns:
            Generated runtime-variable loader helper identifier.
        """
        return f"{self.func_prefix}{lib_id}_load_runtime_vars"

    def gostring_func_name(self) -> str:
        """Build the generated gostring utility function name.

        Returns:
            Generated gostring helper identifier.
        """
        return f"{self.func_prefix}gostring"


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
class GeneratorParseSpec:
    """Generator parse-time configuration prior to header resolution."""

    headers: HeaderConfig
    overlays: tuple[HeaderOverlay, ...]
    filters: GeneratorFilters
    exclude_filters: GeneratorFilters
    clang_args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratorRenderSpec:
    """Generator render-time configuration."""

    naming: GeneratorNaming = field(default_factory=GeneratorNaming)
    helpers: GeneratorHelpers = field(default_factory=GeneratorHelpers)
    type_mapping: TypeMappingOptionsType = field(default_factory=TypeMappingOptions)


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    """Resolved generator configuration prior to env-backed header expansion."""

    lib_id: str
    config_base_dir: PathType
    package: str
    emit_kinds: tuple[str, ...]
    parse: GeneratorParseSpec
    render: GeneratorRenderSpec


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Shared generator config loaded from disk."""

    config_path: PathType
    generator: GeneratorSpec


__all__ = [
    "AppConfig",
    "BufferInputHelper",
    "BufferInputPair",
    "CallbackInputHelper",
    "EnvIncludeHeaders",
    "GeneratorFilters",
    "GeneratorHelpers",
    "GeneratorNaming",
    "GeneratorParseSpec",
    "GeneratorRenderSpec",
    "GeneratorSpec",
    "HeaderConfig",
    "HeaderOverlay",
    "LocalHeaders",
    "OwnedStringReturnHelper",
]
