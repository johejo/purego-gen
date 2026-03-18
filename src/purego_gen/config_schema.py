# Copyright (c) 2026 purego-gen contributors.

"""Shared JSON schema types for generator config."""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Len
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
NonEmptyStrTuple = Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]
FilterValueInput = NonEmptyStr | NonEmptyStrTuple


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TypeMappingInput(_StrictModel):
    """Optional type-mapping overrides."""

    const_char_as_string: StrictBool | None = None
    strict_enum_typedefs: StrictBool | None = None
    typed_sentinel_constants: StrictBool | None = None


class BufferInputPairInput(_StrictModel):
    """One pointer/length parameter pair rewritten by a generated helper."""

    pointer: NonEmptyStr
    length: NonEmptyStr


class BufferInputHelperInput(_StrictModel):
    """One function-specific helper definition for `[]byte` inputs."""

    function: NonEmptyStr
    pairs: Annotated[tuple[BufferInputPairInput, ...], Len(min_length=1)]


class HelpersInput(_StrictModel):
    """Optional helper-generation configuration."""

    buffer_inputs: Annotated[tuple[BufferInputHelperInput, ...], Len(min_length=1)] | None = None


class FiltersInput(_StrictModel):
    """Optional declaration filters."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    func: FilterValueInput | None = None
    type_: FilterValueInput | None = Field(default=None, alias="type")
    const: FilterValueInput | None = None
    var: FilterValueInput | None = None


class LocalHeadersInput(_StrictModel):
    """Header configuration for local file paths."""

    kind: Literal["local"]
    headers: NonEmptyStrTuple


class EnvIncludeHeadersInput(_StrictModel):
    """Header configuration resolved from an include-directory environment variable."""

    kind: Literal["env_include"]
    include_dir_env: NonEmptyStr
    headers: NonEmptyStrTuple


HeaderInput = Annotated[LocalHeadersInput | EnvIncludeHeadersInput, Field(discriminator="kind")]


class GeneratorInput(_StrictModel):
    """Generator configuration loaded from JSON."""

    lib_id: NonEmptyStr
    package: NonEmptyStr
    emit: NonEmptyStr
    headers: HeaderInput
    filters: FiltersInput = Field(default_factory=FiltersInput)
    exclude: FiltersInput = Field(default_factory=FiltersInput)
    helpers: HelpersInput = Field(default_factory=HelpersInput)
    type_mapping: TypeMappingInput = Field(default_factory=TypeMappingInput)
    clang_args: tuple[NonEmptyStr, ...] = ()


class AppConfigInput(_StrictModel):
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
    "HelpersInput",
    "LocalHeadersInput",
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "TypeMappingInput",
]
