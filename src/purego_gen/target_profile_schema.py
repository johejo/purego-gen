# Copyright (c) 2026 purego-gen contributors.

"""Pydantic schemas for target-profile catalog input validation."""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Len
from pydantic import BaseModel, ConfigDict, StringConstraints

from purego_gen.config_schema import TypeMappingInput as SharedTypeMappingInput

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
NonEmptyStrTuple = Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TypeMappingInput(SharedTypeMappingInput):
    """Optional type-mapping overrides for one catalog component."""


class ComponentInput(_StrictModel):
    """Composable profile fields resolved from presets and profile overrides."""

    description: NonEmptyStr | None = None
    header_names: NonEmptyStrTuple | None = None
    emit_kinds: NonEmptyStr | None = None
    required_functions: NonEmptyStrTuple | None = None
    required_types: NonEmptyStrTuple | None = None
    required_constants: NonEmptyStrTuple | None = None
    type_mapping: TypeMappingInput | None = None


class ProfileInput(_StrictModel):
    """One profile entry with compose chain and local overrides."""

    compose: NonEmptyStrTuple
    description: NonEmptyStr | None = None
    header_names: NonEmptyStrTuple | None = None
    emit_kinds: NonEmptyStr | None = None
    required_functions: NonEmptyStrTuple | None = None
    required_types: NonEmptyStrTuple | None = None
    required_constants: NonEmptyStrTuple | None = None
    type_mapping: TypeMappingInput | None = None


class CatalogInput(_StrictModel):
    """Top-level target-profile catalog schema."""

    schema_version: Literal[1]
    description: NonEmptyStr | None = None
    presets: Annotated[dict[NonEmptyStr, ComponentInput], Len(min_length=1)]
    profiles: Annotated[dict[NonEmptyStr, ProfileInput], Len(min_length=1)]
