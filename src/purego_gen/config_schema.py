# Copyright (c) 2026 purego-gen contributors.

"""Shared JSON schema types for generator config."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from annotated_types import Len
from pydantic import ConfigDict, Field, model_validator

from purego_gen.config_shared import NonEmptyStr, NonEmptyStrTuple, StrictModel, TypeMappingInput

FilterValueInput = NonEmptyStr | NonEmptyStrTuple


class PublicApiPatternInput(StrictModel):
    """Regex pattern for public API include/exclude matching."""

    pattern: NonEmptyStr


PublicApiFilterItem = NonEmptyStr | PublicApiPatternInput
PublicApiFilterList = Annotated[tuple[PublicApiFilterItem, ...], Len(min_length=1)]


class PublicApiTypeAliasesInput(StrictModel):
    """Public API type alias generation configuration."""

    include: PublicApiFilterList
    exclude: PublicApiFilterList | None = None
    overrides: dict[str, NonEmptyStr] | None = None


class PublicApiWrappersInput(StrictModel):
    """Public API wrapper function generation configuration."""

    include: PublicApiFilterList
    exclude: PublicApiFilterList | None = None
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


class BufferInputHelperInput(StrictModel):
    """One function-specific helper definition for `[]byte` inputs."""

    function: NonEmptyStr
    pairs: Annotated[tuple[BufferInputPairInput, ...], Len(min_length=1)]


class BufferInputPatternHelperInput(StrictModel):
    """Pattern-based buffer input helper that auto-detects (pointer, length) pairs."""

    function_pattern: NonEmptyStr = Field(
        description="Regex matched via re.search (partial match, not full match)."
    )


class CallbackInputHelperInput(StrictModel):
    """One function-specific helper definition for callback parameters."""

    function: NonEmptyStr
    parameters: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class OwnedStringReturnHelperInput(StrictModel):
    """One function-specific helper definition for owned ``const char *`` returns."""

    function: NonEmptyStr | None = None
    function_pattern: NonEmptyStr | None = Field(
        default=None, description="Regex matched via re.search (partial match, not full match)."
    )
    free_func: NonEmptyStr

    @model_validator(mode="after")
    def _exactly_one_function_spec(self) -> Self:
        if self.function is not None and self.function_pattern is not None:
            message = "exactly one of 'function' or 'function_pattern' must be set, got both"
            raise ValueError(message)
        if self.function is None and self.function_pattern is None:
            message = "exactly one of 'function' or 'function_pattern' must be set, got neither"
            raise ValueError(message)
        return self


class NullableStringInputHelperInput(StrictModel):
    """Override ``string`` params to ``uintptr`` for nullable C strings."""

    function: NonEmptyStr
    parameters: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class OutputStringParamHelperInput(StrictModel):
    """One function-specific helper that overrides ``uintptr`` output params to ``*uintptr``."""

    function: NonEmptyStr
    parameters: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class HelpersInput(StrictModel):
    """Optional helper-generation configuration."""

    auto_callback_inputs: bool = False
    buffer_inputs: (
        Annotated[
            tuple[BufferInputHelperInput | BufferInputPatternHelperInput, ...], Len(min_length=1)
        ]
        | None
    ) = None
    callback_inputs: Annotated[tuple[CallbackInputHelperInput, ...], Len(min_length=1)] | None = (
        None
    )
    owned_string_returns: (
        Annotated[tuple[OwnedStringReturnHelperInput, ...], Len(min_length=1)] | None
    ) = None
    nullable_string_inputs: (
        Annotated[tuple[NullableStringInputHelperInput, ...], Len(min_length=1)] | None
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
    filters: FiltersInput = Field(default_factory=FiltersInput)
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
    public_api: PublicApiInput | None = None


class GeneratorInput(StrictModel):
    """Generator configuration loaded from JSON."""

    lib_id: NonEmptyStr
    package: NonEmptyStr
    emit: NonEmptyStr
    parse: ParseInput
    render: RenderInput = Field(default_factory=RenderInput)


class AppConfigInput(StrictModel):
    """Top-level shared config file."""

    schema_version: Literal[1]
    generator: GeneratorInput


__all__ = [
    "AppConfigInput",
    "EnvIncludeHeadersInput",
    "FilterValueInput",
    "FiltersInput",
    "GeneratorInput",
    "HeaderInput",
    "HeaderOverlayInput",
    "HelpersInput",
    "LocalHeadersInput",
    "NamingInput",
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "ParseInput",
    "PublicApiInput",
    "PublicApiPatternInput",
    "PublicApiTypeAliasesInput",
    "PublicApiWrappersInput",
    "RenderInput",
    "TypeMappingInput",
]
