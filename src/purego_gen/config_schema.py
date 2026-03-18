# Copyright (c) 2026 purego-gen contributors.

"""Shared JSON schema types for generator config."""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Len
from pydantic import ConfigDict, Field

from purego_gen.config_shared import NonEmptyStr, NonEmptyStrTuple, StrictModel, TypeMappingInput

FilterValueInput = NonEmptyStr | NonEmptyStrTuple


class BufferInputPairInput(StrictModel):
    """One pointer/length parameter pair rewritten by a generated helper."""

    pointer: NonEmptyStr
    length: NonEmptyStr


class BufferInputHelperInput(StrictModel):
    """One function-specific helper definition for `[]byte` inputs."""

    function: NonEmptyStr
    pairs: Annotated[tuple[BufferInputPairInput, ...], Len(min_length=1)]


class CallbackInputHelperInput(StrictModel):
    """One function-specific helper definition for callback parameters."""

    function: NonEmptyStr
    parameters: Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class HelpersInput(StrictModel):
    """Optional helper-generation configuration."""

    buffer_inputs: Annotated[tuple[BufferInputHelperInput, ...], Len(min_length=1)] | None = None
    callback_inputs: Annotated[tuple[CallbackInputHelperInput, ...], Len(min_length=1)] | None = (
        None
    )


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


class GeneratorInput(StrictModel):
    """Generator configuration loaded from JSON."""

    lib_id: NonEmptyStr
    identifier_prefix: NonEmptyStr = "purego_"
    package: NonEmptyStr
    emit: NonEmptyStr
    headers: HeaderInput
    overlays: Annotated[tuple[HeaderOverlayInput, ...], Len(min_length=1)] | None = None
    filters: FiltersInput = Field(default_factory=FiltersInput)
    exclude: FiltersInput = Field(default_factory=FiltersInput)
    helpers: HelpersInput = Field(default_factory=HelpersInput)
    type_mapping: TypeMappingInput = Field(default_factory=TypeMappingInput)
    clang_args: tuple[NonEmptyStr, ...] = ()


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
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "TypeMappingInput",
]
