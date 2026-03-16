# Copyright (c) 2026 purego-gen contributors.

"""Compatibility re-exports for shared config schema types."""

from __future__ import annotations

from purego_gen.config import (
    AppConfigInput,
    CompileCRuntimeInput,
    EnvIncludeHeadersInput,
    EnvLibdirRuntimeInput,
    GoldenInput,
    HeaderInput,
    LocalHeadersInput,
    NonEmptyStr,
    NonEmptyStrTuple,
    RuntimeInput,
    TypeMappingInput,
)
from purego_gen.config import FiltersInput as CaseFiltersInput

CaseProfileInput = AppConfigInput

__all__ = [
    "AppConfigInput",
    "CaseFiltersInput",
    "CaseProfileInput",
    "CompileCRuntimeInput",
    "EnvIncludeHeadersInput",
    "EnvLibdirRuntimeInput",
    "GoldenInput",
    "HeaderInput",
    "LocalHeadersInput",
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "RuntimeInput",
    "TypeMappingInput",
]
