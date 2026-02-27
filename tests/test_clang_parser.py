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
    TypeMappingOptions,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_MACRO_CONSTANTS_HEADER = _FIXTURES_DIR / "macro_constants.h"
_FUNCTION_SIGNATURES_HEADER = _FIXTURES_DIR / "function_signatures.h"
_PARAMETER_NAMES_HEADER = _FIXTURES_DIR / "parameter_names.h"
_COMMENTS_HEADER = _FIXTURES_DIR / "comments.h"
_EXPECTED_FIXTURE_MACRO_SEED = 7
_EXPECTED_FIXTURE_VERSION_NUMBER = 10203
_EXPECTED_FIXTURE_MAGIC_NUMBER = 4247762216
_EXPECTED_FIXTURE_CONTENTSIZE_UNKNOWN = 18446744073709551615
_EXPECTED_FIXTURE_CONTENTSIZE_ERROR = 18446744073709551614


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
    """Parser should keep M3 baseline mappings stable for common typedef patterns."""
    header = _FIXTURES_DIR / "abi_types.h"

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
        "fixture_opaque_t",
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
    assert typedef_map["fixture_opaque_t"] == "uintptr"
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
    assert tuple(constant.name for constant in declarations.constants) == (
        "FIXTURE_MODE_OFF",
        "FIXTURE_MODE_ON",
    )


def test_parse_object_like_macro_constants() -> None:
    """Parser should extract object-like integer macros as compile-time constants."""
    declarations = parse_declarations(headers=(str(_MACRO_CONSTANTS_HEADER),), clang_args=())

    constant_map = {constant.name: constant.value for constant in declarations.constants}
    assert set(constant_map) == {
        "FIXTURE_MACRO_SEED",
        "FIXTURE_VERSION_MAJOR",
        "FIXTURE_VERSION_MINOR",
        "FIXTURE_VERSION_PATCH",
        "FIXTURE_VERSION_NUMBER",
        "FIXTURE_MAGIC_NUMBER",
        "FIXTURE_CONTENTSIZE_UNKNOWN",
        "FIXTURE_CONTENTSIZE_ERROR",
    }
    assert constant_map["FIXTURE_MACRO_SEED"] == _EXPECTED_FIXTURE_MACRO_SEED
    assert constant_map["FIXTURE_VERSION_NUMBER"] == _EXPECTED_FIXTURE_VERSION_NUMBER
    assert constant_map["FIXTURE_MAGIC_NUMBER"] == _EXPECTED_FIXTURE_MAGIC_NUMBER
    assert constant_map["FIXTURE_CONTENTSIZE_UNKNOWN"] == _EXPECTED_FIXTURE_CONTENTSIZE_UNKNOWN
    assert constant_map["FIXTURE_CONTENTSIZE_ERROR"] == _EXPECTED_FIXTURE_CONTENTSIZE_ERROR


def test_parse_function_signature_char_pointer_rules() -> None:
    """Parser should apply function-signature char/void pointer mapping rules."""
    declarations_default = parse_declarations(
        headers=(str(_FUNCTION_SIGNATURES_HEADER),), clang_args=()
    )
    function_map_default = {function.name: function for function in declarations_default.functions}
    declarations_enabled = parse_declarations(
        headers=(str(_FUNCTION_SIGNATURES_HEADER),),
        clang_args=(),
        type_mapping=TypeMappingOptions(const_char_as_string=True),
    )
    function_map = {function.name: function for function in declarations_enabled.functions}
    assert tuple(function_map) == (
        "fixture_const_name",
        "fixture_lookup_name",
        "fixture_mutable_name",
        "fixture_fill_name",
        "fixture_user_data",
    )
    assert function_map_default["fixture_const_name"].go_result_type == "uintptr"
    assert function_map_default["fixture_lookup_name"].go_parameter_types == ("uintptr",)
    assert function_map_default["fixture_lookup_name"].go_result_type == "uintptr"
    assert function_map["fixture_const_name"].go_result_type == "string"
    assert function_map["fixture_lookup_name"].go_parameter_types == ("string",)
    assert function_map["fixture_lookup_name"].go_result_type == "string"
    assert function_map["fixture_mutable_name"].go_result_type == "uintptr"
    assert function_map["fixture_fill_name"].go_parameter_types == ("uintptr", "string")
    assert function_map["fixture_user_data"].go_parameter_types == ("uintptr", "uintptr")
    assert function_map["fixture_user_data"].go_result_type == "uintptr"
    assert function_map["fixture_lookup_name"].parameter_names == ("key",)
    assert function_map["fixture_fill_name"].parameter_names == ("dst", "src")
    assert function_map["fixture_user_data"].parameter_names == ("ctx", "src")


def test_parse_function_parameter_names() -> None:
    """Parser should preserve C parameter names, including unnamed parameters."""
    declarations = parse_declarations(headers=(str(_PARAMETER_NAMES_HEADER),), clang_args=())
    function_map = {function.name: function for function in declarations.functions}

    assert function_map["fixture_named_params"].parameter_names == ("lhs", "rhs")
    assert function_map["fixture_unnamed_first"].parameter_names == ("", "rhs")
    assert function_map["fixture_keyword_name"].parameter_names == ("map",)
    assert function_map["fixture_underscore_name"].parameter_names == ("_",)
    assert function_map["fixture_fallback_name_collision"].parameter_names == ("arg2", "")


def test_parse_declaration_comments_default_and_parse_all_comments() -> None:
    """Parser should extract declaration comments from libclang when available."""
    default_declarations = parse_declarations(headers=(str(_COMMENTS_HEADER),), clang_args=())
    parse_all_declarations = parse_declarations(
        headers=(str(_COMMENTS_HEADER),),
        clang_args=("-fparse-all-comments",),
    )

    default_typedef_comments = {
        typedef.name: typedef.comment for typedef in default_declarations.typedefs
    }
    parse_all_typedef_comments = {
        typedef.name: typedef.comment for typedef in parse_all_declarations.typedefs
    }
    assert default_typedef_comments["fixture_doc_type_t"] == "/** Doxygen typedef comment. */"
    assert default_typedef_comments["fixture_plain_type_t"] is None
    assert parse_all_typedef_comments["fixture_plain_type_t"] == "/* Plain typedef comment. */"

    default_constant_comments = {
        constant.name: constant.comment for constant in default_declarations.constants
    }
    parse_all_constant_comments = {
        constant.name: constant.comment for constant in parse_all_declarations.constants
    }
    assert default_constant_comments["FIXTURE_DOC_STATUS"] == "/// Doxygen enum constant comment."
    assert default_constant_comments["FIXTURE_PLAIN_STATUS"] is None
    assert parse_all_constant_comments["FIXTURE_PLAIN_STATUS"] == "// Plain enum constant comment."

    default_function_comments = {
        function.name: function.comment for function in default_declarations.functions
    }
    parse_all_function_comments = {
        function.name: function.comment for function in parse_all_declarations.functions
    }
    assert default_function_comments["fixture_doc_add"] == "/// Doxygen function comment."
    assert default_function_comments["fixture_plain_add"] is None
    assert parse_all_function_comments["fixture_plain_add"] == "// Plain function comment."

    default_runtime_var_comments = {
        runtime_var.name: runtime_var.comment for runtime_var in default_declarations.runtime_vars
    }
    parse_all_runtime_var_comments = {
        runtime_var.name: runtime_var.comment for runtime_var in parse_all_declarations.runtime_vars
    }
    assert default_runtime_var_comments["fixture_doc_counter"] == "/// Doxygen runtime-var comment."
    assert default_runtime_var_comments["fixture_plain_counter"] is None
    assert (
        parse_all_runtime_var_comments["fixture_plain_counter"] == "// Plain runtime-var comment."
    )
