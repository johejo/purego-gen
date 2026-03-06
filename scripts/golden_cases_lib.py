# Copyright (c) 2026 purego-gen contributors.

"""Compatibility wrapper for the packaged golden-cases library."""

from purego_gen_e2e.golden_cases_lib import (
    CompileCRuntime,
    EnvIncludeHeaders,
    EnvLibdirRuntime,
    GoldenCase,
    LocalHeaders,
    check_cases,
    discover_cases,
    resolve_env_libdir_runtime_library,
    update_cases,
)

__all__ = [
    "CompileCRuntime",
    "EnvIncludeHeaders",
    "EnvLibdirRuntime",
    "GoldenCase",
    "LocalHeaders",
    "check_cases",
    "discover_cases",
    "resolve_env_libdir_runtime_library",
    "update_cases",
]
