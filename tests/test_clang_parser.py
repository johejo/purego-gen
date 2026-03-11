# Copyright (c) 2026 purego-gen contributors.

"""Tests for libclang declaration extraction."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_parser import parse_declarations

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def _go_struct(*fields: str) -> str:
    return "struct {\n" + "\n".join(f"\t{field}" for field in fields) + "\n}"


def test_parse_declaration_categories() -> None:
    """Parser should classify declarations into func/type/const/var categories."""
    header = _FIXTURES_DIR / "categories.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    assert tuple(function.name for function in declarations.functions) == ("add",)
    assert tuple(typedef.name for typedef in declarations.typedefs) == ("my_uint",)
    assert tuple(constant.name for constant in declarations.constants) == (
        "FIXTURE_STATUS_OK",
        "FIXTURE_STATUS_NG",
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
    """Parser should keep representative ABI type mappings stable."""
    header = _FIXTURES_DIR / "abi_types.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    assert tuple(function.name for function in declarations.functions) == ()
    assert tuple(runtime_var.name for runtime_var in declarations.runtime_vars) == ()
    typedef_map = {typedef.name: typedef.go_type for typedef in declarations.typedefs}
    assert typedef_map["fixture_mode_t"] == "int32"
    assert typedef_map["fixture_callback_t"] == "uintptr"
    fixture_point_struct_type = _go_struct(
        "left int32",
        "right int32",
        "mode int32",
        "label uintptr",
    )
    fixture_array_struct_type = _go_struct("values [4]int32")
    assert typedef_map["fixture_point_t"] == fixture_point_struct_type
    assert typedef_map["fixture_with_array_t"] == fixture_array_struct_type
    assert typedef_map["fixture_opaque_t"] == "uintptr"

    assert tuple(typedef_map) == (
        "fixture_mode_t",
        "fixture_mode_alias_t",
        "fixture_callback_t",
        "fixture_name_t",
        "fixture_context_t",
        "fixture_point_t",
        "fixture_point_alias_t",
        "fixture_nested_point_t",
        "fixture_with_array_t",
        "fixture_opaque_t",
    )
    assert tuple(typedef.name for typedef in declarations.skipped_typedefs) == (
        "fixture_union_t",
        "fixture_with_bitfield_t",
        "fixture_with_anonymous_field_t",
    )
    assert tuple(constant.name for constant in declarations.constants) == (
        "FIXTURE_MODE_OFF",
        "FIXTURE_MODE_ON",
    )
