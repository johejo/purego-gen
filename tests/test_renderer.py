# Copyright (c) 2026 purego-gen contributors.

"""Tests for Jinja2 renderer behavior."""

from __future__ import annotations

import pytest

from purego_gen.config_model import BufferInputHelper, BufferInputPair, GeneratorHelpers
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
    RecordFieldDecl,
    RecordTypedefDecl,
    TypedefDecl,
    TypeMappingOptions,
)
from purego_gen.renderer import RendererError, RenderOptions, render_go_source, render_template

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
                "helpers": (),
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
                    unsupported_code=TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
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


def test_render_go_source_reuses_record_alias_for_by_value_function_signatures() -> None:
    """Function signatures should reuse emitted record aliases for by-value types."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="roundtrip_point",
                    result_c_type="fixture_point_t",
                    parameter_c_types=("fixture_point_t",),
                    parameter_names=("value",),
                    go_result_type="struct {\n\tleft int32\n\tright int32\n}",
                    go_parameter_types=("struct {\n\tleft int32\n\tright int32\n}",),
                ),
            ),
            typedefs=(
                TypedefDecl(
                    name="fixture_point_t",
                    c_type="struct fixture_point",
                    go_type="struct {\n\tleft int32\n\tright int32\n}",
                ),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                RecordTypedefDecl(
                    name="fixture_point_t",
                    c_type="struct fixture_point",
                    record_kind="STRUCT_DECL",
                    size_bytes=8,
                    align_bytes=4,
                    fields=(
                        RecordFieldDecl(
                            name="left",
                            c_type="int",
                            kind="FIELD_DECL",
                            offset_bits=0,
                            size_bytes=4,
                            align_bytes=4,
                            is_bitfield=False,
                            bitfield_width=None,
                            supported=True,
                            unsupported_code=None,
                            unsupported_reason=None,
                        ),
                        RecordFieldDecl(
                            name="right",
                            c_type="int",
                            kind="FIELD_DECL",
                            offset_bits=32,
                            size_bytes=4,
                            align_bytes=4,
                            is_bitfield=False,
                            bitfield_width=None,
                            supported=True,
                            unsupported_code=None,
                            unsupported_reason=None,
                        ),
                    ),
                    supported=True,
                    unsupported_code=None,
                    unsupported_reason=None,
                ),
            ),
        ),
    )

    normalized_source = " ".join(source.split())
    assert "purego_type_fixture_point_t = struct {" in source
    assert (
        "purego_func_roundtrip_point func( value purego_type_fixture_point_t, ) "
        "purego_type_fixture_point_t"
    ) in normalized_source


def test_render_go_source_keeps_primitive_function_signature_types() -> None:
    """Primitive typedef-backed function signatures should keep primitive Go types."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="current_mode",
                    result_c_type="fixture_mode_t",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type="int32",
                    go_parameter_types=(),
                ),
            ),
            typedefs=(TypedefDecl(name="fixture_mode_t", c_type="int", go_type="int32"),),
            constants=(),
            runtime_vars=(),
        ),
    )

    normalized_source = " ".join(source.split())
    assert "purego_type_fixture_mode_t = int32" in source
    assert "purego_func_current_mode func() int32" in normalized_source
    assert '"unsafe"' not in source


def test_render_go_source_reuses_function_pointer_typedef_aliases() -> None:
    """Anonymous function-pointer slots should reuse emitted typedef aliases."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="run_callback",
                    result_c_type="int",
                    parameter_c_types=("int (*)(void *, int)",),
                    parameter_names=("callback",),
                    go_result_type="int32",
                    go_parameter_types=("uintptr",),
                ),
            ),
            typedefs=(
                TypedefDecl(
                    name="fixture_callback_t",
                    c_type="int (*)(void *, int)",
                    go_type="uintptr",
                ),
            ),
            constants=(),
            runtime_vars=(),
        ),
    )

    normalized_source = " ".join(source.split())
    assert "purego_type_fixture_callback_t = uintptr" in source
    assert (
        "purego_func_run_callback func( callback purego_type_fixture_callback_t, ) int32"
        in normalized_source
    )


def test_render_go_source_types_casted_sentinel_constants_with_typedef_alias() -> None:
    """Typed sentinel constants should reuse emitted typedef aliases and expressions."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("const", "type"),
        declarations=ParsedDeclarations(
            functions=(),
            typedefs=(
                TypedefDecl(
                    name="fixture_destructor_t",
                    c_type="void (*)(void *)",
                    go_type="uintptr",
                ),
            ),
            constants=(
                ConstantDecl(
                    name="FIXTURE_STATIC",
                    value=0,
                    c_type="fixture_destructor_t",
                ),
                ConstantDecl(
                    name="FIXTURE_TRANSIENT",
                    value=(1 << 64) - 1,
                    c_type="fixture_destructor_t",
                    go_expression="^uintptr(0)",
                ),
            ),
            runtime_vars=(),
        ),
        options=RenderOptions(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(typed_sentinel_constants=True),
        ),
    )

    assert "purego_const_FIXTURE_STATIC purego_type_fixture_destructor_t = 0" in source
    assert "purego_const_FIXTURE_TRANSIENT purego_type_fixture_destructor_t = ^uintptr(0)" in source


def test_render_go_source_emits_buffer_input_helper_functions() -> None:
    """Configured buffer-input helpers should generate `[]byte` wrappers."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_consume_bytes",
                    result_c_type="int",
                    parameter_c_types=("const void *", "size_t", "uint32_t"),
                    parameter_names=("data", "data_len", "flags"),
                    go_result_type="int32",
                    go_parameter_types=("uintptr", "uint64", "uint32"),
                ),
            ),
            typedefs=(),
            constants=(),
            runtime_vars=(),
        ),
        options=RenderOptions(
            helpers=GeneratorHelpers(
                buffer_inputs=(
                    BufferInputHelper(
                        function="fixture_consume_bytes",
                        pairs=(BufferInputPair(pointer="data", length="data_len"),),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    normalized_source = " ".join(source.split())
    assert '"unsafe"' in source
    assert "func purego_func_fixture_consume_bytes_bytes(" in source
    assert (
        "func purego_func_fixture_consume_bytes_bytes( data []byte, flags uint32, ) int32 {"
        in normalized_source
    )
    assert "data_ptr := uintptr(0)" in source
    assert "if len(data_len) > 0 {" in source
    assert "data_ptr = uintptr(unsafe.Pointer(&data_len[0]))" in source
    assert (
        "return purego_func_fixture_consume_bytes( data_ptr, uint64(len(data_len)), flags, )"
        in normalized_source
    )


def test_render_go_source_rejects_missing_buffer_helper_function() -> None:
    """Buffer-input helpers should fail when the target function is missing."""
    with pytest.raises(
        RendererError,
        match=r"buffer helper target function not found: fixture_consume_bytes",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            options=RenderOptions(
                helpers=GeneratorHelpers(
                    buffer_inputs=(
                        BufferInputHelper(
                            function="fixture_consume_bytes",
                            pairs=(BufferInputPair(pointer="data", length="data_len"),),
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_render_go_source_rejects_non_void_pointer_buffer_helper() -> None:
    """Buffer-input helpers should reject pointer parameters outside `const void *`."""
    with pytest.raises(
        RendererError,
        match=r"parameter data must be `const void \*`, got `const char \*`",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fixture_consume_bytes",
                        result_c_type="int",
                        parameter_c_types=("const char *", "size_t"),
                        parameter_names=("data", "data_len"),
                        go_result_type="int32",
                        go_parameter_types=("string", "uint64"),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            options=RenderOptions(
                helpers=GeneratorHelpers(
                    buffer_inputs=(
                        BufferInputHelper(
                            function="fixture_consume_bytes",
                            pairs=(BufferInputPair(pointer="data", length="data_len"),),
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )
