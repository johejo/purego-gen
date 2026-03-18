# Copyright (c) 2026 purego-gen contributors.

"""Pydantic schemas for target-profile catalog input validation."""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Len

from purego_gen.config_shared import NonEmptyStr, NonEmptyStrTuple, StrictModel, TypeMappingInput


class ComponentInput(StrictModel):
    """Composable profile fields resolved from presets and profile overrides."""

    description: NonEmptyStr | None = None
    header_names: NonEmptyStrTuple | None = None
    emit_kinds: NonEmptyStr | None = None
    required_functions: NonEmptyStrTuple | None = None
    required_types: NonEmptyStrTuple | None = None
    required_constants: NonEmptyStrTuple | None = None
    type_mapping: TypeMappingInput | None = None


class ProfileInput(StrictModel):
    """One profile entry with compose chain and local overrides."""

    compose: NonEmptyStrTuple
    description: NonEmptyStr | None = None
    header_names: NonEmptyStrTuple | None = None
    emit_kinds: NonEmptyStr | None = None
    required_functions: NonEmptyStrTuple | None = None
    required_types: NonEmptyStrTuple | None = None
    required_constants: NonEmptyStrTuple | None = None
    type_mapping: TypeMappingInput | None = None


class CatalogInput(StrictModel):
    """Top-level target-profile catalog schema."""

    schema_version: Literal[1]
    description: NonEmptyStr | None = None
    presets: Annotated[dict[NonEmptyStr, ComponentInput], Len(min_length=1)]
    profiles: Annotated[dict[NonEmptyStr, ProfileInput], Len(min_length=1)]
