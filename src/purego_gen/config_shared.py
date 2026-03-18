# Copyright (c) 2026 purego-gen contributors.

"""Shared schema primitives and config helpers."""

from __future__ import annotations

from typing import Annotated

from annotated_types import Len
from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
NonEmptyStrTuple = Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class StrictModel(BaseModel):
    """Base schema model with strict extra-forbidden validation."""

    model_config = ConfigDict(extra="forbid", strict=True)


class TypeMappingInput(StrictModel):
    """Optional type-mapping overrides."""

    const_char_as_string: StrictBool | None = None
    strict_enum_typedefs: StrictBool | None = None
    typed_sentinel_constants: StrictBool | None = None


def type_mapping_input_to_dict(type_mapping: TypeMappingInput | None) -> dict[str, bool] | None:
    """Convert optional type-mapping input to sparse boolean overrides.

    Returns:
        Explicitly configured type-mapping flags, or `None` when unset.
    """
    if type_mapping is None:
        return None
    return dict(type_mapping.model_dump(exclude_none=True))


__all__ = [
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "StrictModel",
    "TypeMappingInput",
    "type_mapping_input_to_dict",
]
