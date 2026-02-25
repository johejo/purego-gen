# Copyright (c) 2026 purego-gen contributors.

"""Tests for libclang declaration extraction."""

from __future__ import annotations

from pathlib import Path

from purego_gen.clang_parser import parse_declarations
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


def _go_struct(*fields: str) -> str:
    return "struct {\n" + "\n".join(f"\t{field}" for field in fields) + "\n}"


def test_parse_declaration_categories() -> None:
    """Parser should classify declarations into func/type/const/var categories."""
    header = _FIXTURES_DIR / "sample_categories.h"

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
    """Parser should keep M3 baseline mappings stable for common typedef patterns."""
    header = _FIXTURES_DIR / "sample_m3_types.h"

    declarations = parse_declarations(headers=(str(header),), clang_args=())

    assert tuple(function.name for function in declarations.functions) == ()
    assert tuple(runtime_var.name for runtime_var in declarations.runtime_vars) == ()
    typedef_map = {typedef.name: typedef.go_type for typedef in declarations.typedefs}
    assert tuple(typedef_map) == (
        "fixture_mode_t",
        "fixture_mode_alias_t",
        "fixture_callback_t",
        "fixture_name_t",
        "fixture_context_t",
        "fixture_point_t",
        "fixture_point_alias_t",
        "fixture_nested_point_t",
    )
    assert typedef_map["fixture_mode_t"] == "int32"
    assert typedef_map["fixture_mode_alias_t"] == "int32"
    assert typedef_map["fixture_callback_t"] == "uintptr"
    assert typedef_map["fixture_name_t"] == "uintptr"
    assert typedef_map["fixture_context_t"] == "uintptr"
    point_struct_type = _go_struct(
        "left int32",
        "right int32",
        "mode int32",
        "label uintptr",
    )
    assert typedef_map["fixture_point_t"] == point_struct_type
    assert typedef_map["fixture_point_alias_t"] == point_struct_type
    assert typedef_map["fixture_nested_point_t"] == _go_struct(
        f"point {point_struct_type}",
        f"inner {_go_struct('level int32')}",
    )
    assert "fixture_with_array_t" not in typedef_map
    assert "fixture_union_t" not in typedef_map
    assert "fixture_with_bitfield_t" not in typedef_map
    assert "fixture_with_anonymous_field_t" not in typedef_map
    assert "fixture_opaque_t" not in typedef_map
    skipped_typedef_map = {
        typedef.name: (typedef.reason_code, typedef.reason)
        for typedef in declarations.skipped_typedefs
    }
    array_code, array_reason = skipped_typedef_map["fixture_with_array_t"]
    assert array_code == TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE
    assert "unsupported field type for values:" in array_reason
    assert "[4]" in array_reason
    assert skipped_typedef_map["fixture_union_t"] == (
        TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
        "union typedefs are not supported in v1",
    )
    assert skipped_typedef_map["fixture_with_bitfield_t"] == (
        TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
        "bitfield flags is not supported in v1",
    )
    assert skipped_typedef_map["fixture_with_anonymous_field_t"] == (
        TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
        "struct has no supported fields in v1",
    )
    assert skipped_typedef_map["fixture_opaque_t"] == (
        TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
        "struct has no supported fields in v1",
    )
    assert tuple(constant.name for constant in declarations.constants) == (
        "FIXTURE_MODE_OFF",
        "FIXTURE_MODE_ON",
    )
