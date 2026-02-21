# Copyright (c) 2026 purego-gen contributors.

"""Tests for libclang declaration extraction."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_parser import parse_declarations

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def test_parse_declaration_categories() -> None:
    """Parser should classify declarations into func/type/const/var categories."""
    header = _FIXTURES_DIR / "sample_categories.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    assert tuple(function.name for function in declarations.functions) == ("add",)
    assert tuple(typedef.name for typedef in declarations.typedefs) == ("my_uint",)
    assert tuple(constant.name for constant in declarations.constants) == (
        "SAMPLE_STATUS_OK",
        "SAMPLE_STATUS_NG",
    )
    assert tuple(constant.value for constant in declarations.constants) == (0, 2)
    assert tuple(runtime_var.name for runtime_var in declarations.runtime_vars) == (
        "global_counter",
        "build_id",
    )

    constant_names = {constant.name for constant in declarations.constants}
    runtime_var_names = {runtime_var.name for runtime_var in declarations.runtime_vars}
    assert "global_counter" not in constant_names
    assert "build_id" not in constant_names
    assert constant_names.isdisjoint(runtime_var_names)


def test_parse_type_mapping_edge_cases() -> None:
    """Parser should keep M3 baseline mappings stable for common typedef patterns."""
    header = _FIXTURES_DIR / "sample_m3_types.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    assert tuple(function.name for function in declarations.functions) == ()
    assert tuple(runtime_var.name for runtime_var in declarations.runtime_vars) == ()
    assert tuple((typedef.name, typedef.go_type) for typedef in declarations.typedefs) == (
        ("sample_mode_t", "int32"),
        ("sample_mode_alias_t", "int32"),
        ("sample_callback_t", "uintptr"),
        ("sample_name_t", "uintptr"),
        ("sample_context_t", "uintptr"),
    )
    assert tuple(constant.name for constant in declarations.constants) == (
        "SAMPLE_MODE_OFF",
        "SAMPLE_MODE_ON",
    )
