# Copyright (c) 2026 purego-gen contributors.

"""Shared JSON schema types for generator config."""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Len
from pydantic import ConfigDict, Field

from purego_gen.config_shared import NonEmptyStr, NonEmptyStrTuple, StrictModel, TypeMappingInput

EmitKind = Literal["func", "type", "const", "var"]
EmitKindsTuple = Annotated[tuple[EmitKind, ...], Len(min_length=1)]


class PatternInput(StrictModel):
    """Regex pattern for filter/match specifications."""

    pattern: NonEmptyStr


FilterItem = NonEmptyStr | PatternInput
FilterList = Annotated[tuple[FilterItem, ...], Len(min_length=1)]

FunctionMatch = NonEmptyStr | PatternInput

FilterValueInput = FilterItem | FilterList


class PublicApiTypeAliasesInput(StrictModel):
    """Public API type alias generation configuration."""

    include: FilterList
    exclude: FilterList | None = None
    overrides: dict[str, NonEmptyStr] | None = None


class PublicApiWrappersInput(StrictModel):
    """Public API wrapper function generation configuration."""

    include: FilterList
    exclude: FilterList | None = None
    overrides: dict[str, NonEmptyStr] | None = None


class PublicApiInput(StrictModel):
    """Public API glue code generation configuration."""

    strip_prefix: NonEmptyStr | None = None
    type_aliases: PublicApiTypeAliasesInput | None = None
    wrappers: PublicApiWrappersInput | None = None


class BufferInputPairInput(StrictModel):
    """One pointer/length parameter pair rewritten by a generated helper."""

    pointer: NonEmptyStr
    length: NonEmptyStr


class BufferParamHelperInput(StrictModel):
    """One helper definition for `[]byte` input parameters with explicit pairs."""

    function: NonEmptyStr
    pairs: Annotated[tuple[BufferInputPairInput, ...], Len(min_length=1)]


class BufferParamPatternHelperInput(StrictModel):
    """Pattern-based helper definition for `[]byte` input parameters (always auto-detect)."""

    function: PatternInput


class CallbackParamHelperInput(StrictModel):
    """One function-specific helper definition for callback parameters."""

    function: NonEmptyStr
    params: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class OwnedStringReturnHelperInput(StrictModel):
    """One function-specific helper definition for owned ``const char *`` returns."""

    function: FunctionMatch
    free_func: NonEmptyStr


class NullableStringParamHelperInput(StrictModel):
    """Override ``string`` params to ``uintptr`` for nullable C strings."""

    function: NonEmptyStr
    params: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class OutputStringParamHelperInput(StrictModel):
    """One function-specific helper that overrides ``uintptr`` output params to ``*uintptr``."""

    function: NonEmptyStr
    params: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class HelpersInput(StrictModel):
    """Optional helper-generation configuration."""

    buffer_params: (
        Annotated[
            tuple[BufferParamHelperInput | BufferParamPatternHelperInput, ...], Len(min_length=1)
        ]
        | None
    ) = None
    callback_params: Annotated[tuple[CallbackParamHelperInput, ...], Len(min_length=1)] | None = (
        None
    )
    owned_string_returns: (
        Annotated[tuple[OwnedStringReturnHelperInput, ...], Len(min_length=1)] | None
    ) = None
    nullable_string_params: (
        Annotated[tuple[NullableStringParamHelperInput, ...], Len(min_length=1)] | None
    ) = None
    output_string_params: (
        Annotated[tuple[OutputStringParamHelperInput, ...], Len(min_length=1)] | None
    ) = None


class HeaderOverlayInput(StrictModel):
    """One in-memory header overlay presented as a virtual file."""

    path: NonEmptyStr
    content: NonEmptyStr


class FiltersInput(StrictModel):
    """Optional declaration filters."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    func: FilterValueInput | None = None
    type_: FilterValueInput | None = Field(default=None, alias="type")
    const: FilterValueInput | None = None
    var: FilterValueInput | None = None


class LocalHeadersInput(StrictModel):
    """Header configuration for local file paths."""

    kind: Literal["local"]
    headers: NonEmptyStrTuple


class EnvIncludeHeadersInput(StrictModel):
    """Header configuration resolved from an include-directory environment variable."""

    kind: Literal["env_include"]
    include_dir_env: NonEmptyStr
    headers: NonEmptyStrTuple


HeaderInput = Annotated[LocalHeadersInput | EnvIncludeHeadersInput, Field(discriminator="kind")]


class ParseInput(StrictModel):
    """Generator parse-time configuration loaded from JSON."""

    headers: HeaderInput
    overlays: Annotated[tuple[HeaderOverlayInput, ...], Len(min_length=1)] | None = None
    include: FiltersInput = Field(default_factory=FiltersInput)
    exclude: FiltersInput = Field(default_factory=FiltersInput)
    clang_args: tuple[NonEmptyStr, ...] = ()


class NamingInput(StrictModel):
    """Generated Go identifier naming configuration."""

    type_prefix: str = ""
    const_prefix: str = ""
    func_prefix: str = ""
    var_prefix: str = ""


class RenderInput(StrictModel):
    """Generator render-time configuration loaded from JSON."""

    naming: NamingInput = Field(default_factory=NamingInput)
    helpers: HelpersInput = Field(default_factory=HelpersInput)
    type_mapping: TypeMappingInput = Field(default_factory=TypeMappingInput)
    struct_accessors: bool = False
    auto_callbacks: bool = False
    public_api: PublicApiInput | None = None


class GeneratorInput(StrictModel):
    """Generator configuration loaded from JSON."""

    lib_id: NonEmptyStr
    package: NonEmptyStr
    emit: EmitKindsTuple
    parse: ParseInput
    render: RenderInput = Field(default_factory=RenderInput)


class AppConfigInput(StrictModel):
    """Top-level shared config file."""

    schema_version: Literal[2]
    generator: GeneratorInput


__all__ = [
    "AppConfigInput",
    "BufferParamHelperInput",
    "BufferParamPatternHelperInput",
    "CallbackParamHelperInput",
    "EmitKind",
    "EmitKindsTuple",
    "EnvIncludeHeadersInput",
    "FilterItem",
    "FilterList",
    "FilterValueInput",
    "FiltersInput",
    "FunctionMatch",
    "GeneratorInput",
    "HeaderInput",
    "HeaderOverlayInput",
    "HelpersInput",
    "LocalHeadersInput",
    "NamingInput",
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "NullableStringParamHelperInput",
    "OutputStringParamHelperInput",
    "OwnedStringReturnHelperInput",
    "ParseInput",
    "PatternInput",
    "PublicApiInput",
    "PublicApiTypeAliasesInput",
    "PublicApiWrappersInput",
    "RenderInput",
    "TypeMappingInput",
]
