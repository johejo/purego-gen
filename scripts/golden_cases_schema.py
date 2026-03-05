# Copyright (c) 2026 purego-gen contributors.

"""Pydantic schemas for golden case profile validation."""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Len
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
NonEmptyStrTuple = Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CaseFiltersInput(_StrictModel):
    """Optional declaration filters for one case profile."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    func: NonEmptyStr | None = None
    type_: NonEmptyStr | None = Field(default=None, alias="type")
    const: NonEmptyStr | None = None
    var: NonEmptyStr | None = None


class LocalHeadersInput(_StrictModel):
    """Header configuration for case-local header file paths."""

    kind: Literal["local"]
    paths: NonEmptyStrTuple


class PkgConfigHeadersInput(_StrictModel):
    """Header configuration resolved from pkg-config metadata."""

    kind: Literal["pkg_config"]
    package: NonEmptyStr
    header_names: NonEmptyStrTuple


HeaderInput = Annotated[LocalHeadersInput | PkgConfigHeadersInput, Field(discriminator="kind")]


class CompileCRuntimeInput(_StrictModel):
    """Runtime configuration for case-local C compilation."""

    kind: Literal["compile_c"]
    sources: NonEmptyStrTuple
    cflags: NonEmptyStrTuple | None = None
    ldflags: NonEmptyStrTuple | None = None


class PkgConfigRuntimeInput(_StrictModel):
    """Runtime configuration resolved from pkg-config library metadata."""

    kind: Literal["pkg_config"]
    package: NonEmptyStr
    override_env: NonEmptyStr | None = None
    library_names: NonEmptyStrTuple


RuntimeInput = Annotated[
    CompileCRuntimeInput | PkgConfigRuntimeInput,
    Field(discriminator="kind"),
]


class TypeMappingInput(_StrictModel):
    """Type-mapping options exposed in case profile input."""

    const_char_as_string: StrictBool = False
    strict_enum_typedefs: StrictBool = False
    typed_sentinel_constants: StrictBool = False


class CaseProfileInput(_StrictModel):
    """Top-level schema for one golden case profile file."""

    schema_version: Literal[1]
    lib_id: NonEmptyStr
    package: NonEmptyStr
    emit: NonEmptyStr
    headers: HeaderInput
    filters: CaseFiltersInput = Field(default_factory=CaseFiltersInput)
    type_mapping: TypeMappingInput = Field(default_factory=TypeMappingInput)
    clang_args: NonEmptyStrTuple | None = None
    runtime: RuntimeInput | None = None
