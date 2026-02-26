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


def test_render_go_source_preserves_casing_in_identifiers() -> None:
    """Generated identifiers should preserve source symbol casing."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type", "const", "var"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="ZSTD_compressBound",
                    result_c_type="size_t",
                    parameter_c_types=("size_t",),
                    parameter_names=("srcSize",),
                    go_result_type="uint64",
                    go_parameter_types=("uint64",),
                ),
            ),
            typedefs=(
                TypedefDecl(
                    name="ZSTD_CCtx",
                    c_type="struct ZSTD_CCtx",
                    go_type="uintptr",
                ),
            ),
            constants=(ConstantDecl(name="ZSTD_VERSION_MAJOR", value=1),),
            runtime_vars=(RuntimeVarDecl(name="ZSTD_runtimeValue", c_type="int"),),
        ),
    )
    assert "purego_func_ZSTD_compressBound" in source
    assert "purego_type_ZSTD_CCtx" in source
    assert "purego_const_ZSTD_VERSION_MAJOR" in source
    assert "purego_var_ZSTD_runtimeValue" in source


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


def test_render_go_source_uses_emitted_opaque_aliases_for_function_signatures() -> None:
    """Function signatures should use emitted opaque typedef aliases when available."""
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
                FunctionDecl(
                    name="consume_ctx",
                    result_c_type="void",
                    parameter_c_types=("foo_t *", "const foo_t *"),
                    parameter_names=("ctx", "input"),
                    go_result_type=None,
                    go_parameter_types=("uintptr", "uintptr"),
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
                    unsupported_code="PG_TYPE_NO_SUPPORTED_FIELDS",
                    unsupported_reason="struct has no supported fields in v1",
                ),
            ),
        ),
    )
    normalized_source = " ".join(source.split())
    assert "purego_type_foo_t = uintptr" in source
    assert "purego_func_create_ctx func() purego_type_foo_t" in source
    assert (
        "purego_func_consume_ctx func( ctx purego_type_foo_t, input purego_type_foo_t, )"
        in normalized_source
    )


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
                    unsupported_code="PG_TYPE_NO_SUPPORTED_FIELDS",
                    unsupported_reason="struct has no supported fields in v1",
                ),
            ),
        ),
    )
    normalized_source = " ".join(source.split())
    assert "purego_type_foo_t" not in source
    assert "purego_func_create_ctx func( ctx uintptr, ) uintptr" in normalized_source


def test_render_go_source_preserves_string_function_signatures() -> None:
    """Renderer should keep parser-produced string function signature types."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="lookup_name",
                    result_c_type="const char *",
                    parameter_c_types=("const char *", "void *"),
                    parameter_names=("key", "ctx"),
                    go_result_type="string",
                    go_parameter_types=("string", "uintptr"),
                ),
            ),
            typedefs=(),
            constants=(),
            runtime_vars=(),
        ),
    )
    normalized_source = " ".join(source.split())
    assert "purego_func_lookup_name func( key string, ctx uintptr, ) string" in normalized_source
    assert "purego_bytes_ptr" not in source
    assert "purego_string_ptr" not in source
    assert "purego_string_from_ptr" not in source


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
