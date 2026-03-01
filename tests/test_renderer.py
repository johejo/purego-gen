# Copyright (c) 2026 purego-gen contributors.

"""Tests for Jinja2 renderer behavior."""

from __future__ import annotations

import pytest

from purego_gen.model import (
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
    RecordTypedefDecl,
    RuntimeVarDecl,
    TypedefDecl,
    TypeMappingOptions,
)
from purego_gen.renderer import RendererError, render_go_source, render_template

_FIXTURE_PACKAGE = "fixture"
_FIXTURE_LIB_ID = "fixture_lib"


def test_render_template_requires_all_top_level_context_keys() -> None:
    """Renderer should fail fast when required template keys are missing."""
    with pytest.raises(RendererError, match="template context missing required keys"):
        render_template("go_file.go.j2", {"package": _FIXTURE_PACKAGE})


def test_render_template_fails_on_missing_nested_key() -> None:
    """Strict undefined mode should fail on missing nested values."""
    with pytest.raises(
        RendererError,
        match="template rendering failed due to undefined variable",
    ):
        render_template(
            "go_file.go.j2",
            {
                "package": _FIXTURE_PACKAGE,
                "lib_id": _FIXTURE_LIB_ID,
                "emit_kinds": ("func",),
                "type_aliases": (),
                "constants": (),
                "functions": ({"name": "add"},),
                "runtime_vars": (),
            },
        )


def test_render_go_source_adds_suffix_for_category_local_collisions() -> None:
    """Identifier collisions in the same category should get deterministic suffixes."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "const"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="dup-name",
                    result_c_type="void",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type=None,
                    go_parameter_types=(),
                ),
                FunctionDecl(
                    name="dup_name",
                    result_c_type="void",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type=None,
                    go_parameter_types=(),
                ),
            ),
            typedefs=(),
            constants=(
                ConstantDecl(name="FOO-BAR", value=1),
                ConstantDecl(name="FOO_BAR", value=2),
            ),
            runtime_vars=(),
        ),
    )
    assert "purego_func_dup_name func()" in source
    assert "purego_func_dup_name_2 func()" in source
    assert "purego_const_FOO_BAR = 1" in source
    assert "purego_const_FOO_BAR_2 = 2" in source


def test_render_go_source_falls_back_to_uintptr_without_type_emit() -> None:
    """Function signatures should keep uintptr when type aliases are not emitted."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="create_ctx",
                    result_c_type="foo_t *",
                    parameter_c_types=("const foo_t *",),
                    parameter_names=("ctx",),
                    go_result_type="uintptr",
                    go_parameter_types=("uintptr",),
                ),
            ),
            typedefs=(TypedefDecl(name="foo_t", c_type="struct foo", go_type="uintptr"),),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                RecordTypedefDecl(
                    name="foo_t",
                    c_type="struct foo",
                    record_kind="STRUCT_DECL",
                    size_bytes=None,
                    align_bytes=None,
                    fields=(),
                    supported=False,
                    unsupported_code="PG_TYPE_OPAQUE_INCOMPLETE_STRUCT",
                    unsupported_reason="incomplete struct typedef is treated as opaque handle",
                    is_incomplete=True,
                    is_opaque=True,
                ),
            ),
        ),
    )
    normalized_source = " ".join(source.split())
    assert "purego_type_foo_t" not in source
    assert "purego_func_create_ctx func( ctx uintptr, ) uintptr" in normalized_source


def test_render_go_source_emits_strict_opaque_handle_types_by_default() -> None:
    """Opaque struct handles should emit named strict types by default in v2."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="create_ctx",
                    result_c_type="foo_t *",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type="uintptr",
                    go_parameter_types=(),
                ),
            ),
            typedefs=(
                TypedefDecl(name="foo_t", c_type="struct foo", go_type="uintptr"),
                TypedefDecl(name="my_handle", c_type="void *", go_type="uintptr"),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                RecordTypedefDecl(
                    name="foo_t",
                    c_type="struct foo",
                    record_kind="STRUCT_DECL",
                    size_bytes=None,
                    align_bytes=None,
                    fields=(),
                    supported=False,
                    unsupported_code="PG_TYPE_OPAQUE_INCOMPLETE_STRUCT",
                    unsupported_reason="incomplete struct typedef is treated as opaque handle",
                    is_incomplete=True,
                    is_opaque=True,
                ),
            ),
        ),
    )
    normalized_source = " ".join(source.split())
    assert "purego_type_foo_t uintptr" in normalized_source
    assert "purego_type_foo_t = uintptr" not in source
    assert "purego_type_my_handle = uintptr" in source
    assert "purego_func_create_ctx func() purego_type_foo_t" in source


def test_render_go_source_sanitizes_function_parameter_names_with_fallbacks() -> None:
    """Renderer should sanitize C parameter names and apply stable fallback names."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="test_names",
                    result_c_type="int",
                    parameter_c_types=("int", "int", "int", "int", "int"),
                    parameter_names=("", "_", "map", "same-name", "same_name"),
                    go_result_type="int32",
                    go_parameter_types=("int32", "int32", "int32", "int32", "int32"),
                ),
            ),
            typedefs=(),
            constants=(),
            runtime_vars=(),
        ),
    )
    normalized_source = " ".join(source.split())
    assert (
        "purego_func_test_names func( arg1 int32, arg2 int32, map_ int32, same_name int32, "
        "same_name_2 int32, ) int32" in normalized_source
    )


def test_render_go_source_strict_enum_typedef_mapping_is_opt_in() -> None:
    """Strict enum typedef mode should lift matching function slots to strict aliases."""
    declarations = ParsedDeclarations(
        functions=(
            FunctionDecl(
                name="get_mode",
                result_c_type="fixture_mode_t",
                parameter_c_types=("fixture_mode_t",),
                parameter_names=("mode",),
                go_result_type="int32",
                go_parameter_types=("int32",),
            ),
        ),
        typedefs=(TypedefDecl(name="fixture_mode_t", c_type="enum fixture_mode", go_type="int32"),),
        constants=(),
        runtime_vars=(),
    )
    source_default = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=declarations,
    )
    normalized_default = " ".join(source_default.split())
    assert "purego_type_fixture_mode_t = int32" in source_default
    assert "purego_func_get_mode func( mode int32, ) int32" in normalized_default

    source_strict = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=declarations,
        type_mapping=TypeMappingOptions(strict_enum_typedefs=True),
    )
    normalized_strict = " ".join(source_strict.split())
    assert "purego_type_fixture_mode_t int32" in normalized_strict
    assert "purego_type_fixture_mode_t = int32" not in source_strict
    assert (
        "purego_func_get_mode func( mode purego_type_fixture_mode_t, ) "
        "purego_type_fixture_mode_t" in normalized_strict
    )

    source_strict_without_type_emit = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=declarations,
        type_mapping=TypeMappingOptions(strict_enum_typedefs=True),
    )
    normalized_strict_without_type_emit = " ".join(source_strict_without_type_emit.split())
    assert "purego_type_fixture_mode_t" not in source_strict_without_type_emit
    assert "purego_func_get_mode func( mode int32, ) int32" in normalized_strict_without_type_emit


def test_render_go_source_typed_sentinel_constants_is_opt_in() -> None:
    """Typed sentinel constants mode should annotate large constants as uint64."""
    declarations = ParsedDeclarations(
        functions=(),
        typedefs=(),
        constants=(
            ConstantDecl(name="SMALL_SENTINEL", value=7),
            ConstantDecl(name="BIG_SENTINEL", value=18446744073709551615),
        ),
        runtime_vars=(),
    )
    source_default = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("const",),
        declarations=declarations,
    )
    assert "purego_const_SMALL_SENTINEL = 7" in source_default
    assert "purego_const_BIG_SENTINEL = 18446744073709551615" in source_default

    source_typed = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("const",),
        declarations=declarations,
        type_mapping=TypeMappingOptions(typed_sentinel_constants=True),
    )
    assert "purego_const_SMALL_SENTINEL = 7" in source_typed
    assert "purego_const_BIG_SENTINEL uint64 = 18446744073709551615" in source_typed


def test_render_go_source_copies_comments_before_declarations() -> None:
    """Renderer should normalize raw comments and place them before declarations."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type", "const", "var"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="doc_func",
                    result_c_type="void",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type=None,
                    go_parameter_types=(),
                    comment="/** Function doc line 1.\n *\n * Function doc line 2.\n */",
                ),
                FunctionDecl(
                    name="plain_func",
                    result_c_type="void",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type=None,
                    go_parameter_types=(),
                    comment="// Plain function doc.",
                ),
            ),
            typedefs=(
                TypedefDecl(
                    name="doc_type_t",
                    c_type="int",
                    go_type="int32",
                    comment="/** Type doc line 1.\n *\n * Type doc line 2.\n */",
                ),
                TypedefDecl(
                    name="plain_type_t",
                    c_type="int",
                    go_type="int32",
                    comment="/* Plain type doc. */",
                ),
            ),
            constants=(
                ConstantDecl(
                    name="DOC_CONST",
                    value=1,
                    comment="/// Doxygen constant doc.",
                ),
                ConstantDecl(
                    name="PLAIN_CONST",
                    value=2,
                    comment="// Plain constant doc.",
                ),
            ),
            runtime_vars=(
                RuntimeVarDecl(
                    name="doc_runtime_var",
                    c_type="int",
                    comment="/** Runtime var doc. */",
                ),
                RuntimeVarDecl(
                    name="plain_runtime_var",
                    c_type="int",
                    comment="/* Plain runtime var doc. */",
                ),
            ),
        ),
    )
    normalized_lines = "\n".join(line.strip() for line in source.splitlines())

    assert (
        "// Type doc line 1.\n//\n// Type doc line 2.\npurego_type_doc_type_t = int32"
    ) in normalized_lines
    assert "// Plain type doc.\npurego_type_plain_type_t = int32" in normalized_lines
    assert "// Doxygen constant doc.\npurego_const_DOC_CONST = 1" in normalized_lines
    assert "// Plain constant doc.\npurego_const_PLAIN_CONST = 2" in normalized_lines
    assert (
        "// Function doc line 1.\n//\n// Function doc line 2.\npurego_func_doc_func func()"
    ) in normalized_lines
    assert "// Plain function doc.\npurego_func_plain_func func()" in normalized_lines
    assert "// Runtime var doc.\npurego_var_doc_runtime_var uintptr" in normalized_lines
    assert "// Plain runtime var doc.\npurego_var_plain_runtime_var uintptr" in normalized_lines
