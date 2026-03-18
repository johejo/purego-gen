# Copyright (c) 2026 purego-gen contributors.

"""Tests for Jinja2 renderer behavior."""

from __future__ import annotations

import pytest

from purego_gen.config_model import (
    BufferInputHelper,
    BufferInputPair,
    CallbackInputHelper,
    GeneratorHelpers,
)
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


def test_render_go_source_accepts_generated_names_for_unnamed_buffer_parameters() -> None:
    """Buffer-input helpers should target unnamed parameters via generated arg names."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_bind_blob",
                    result_c_type="int",
                    parameter_c_types=(
                        "stmt_t",
                        "int",
                        "const void *",
                        "size_t",
                        "void (*)(void *)",
                    ),
                    parameter_names=("", "", "", "n", ""),
                    go_result_type="int32",
                    go_parameter_types=("uintptr", "int32", "uintptr", "uint64", "uintptr"),
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
                        function="fixture_bind_blob",
                        pairs=(BufferInputPair(pointer="arg3", length="n"),),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    normalized_source = " ".join(source.split())
    assert "func purego_func_fixture_bind_blob_bytes(" in source
    assert (
        "func purego_func_fixture_bind_blob_bytes("
        " arg1 uintptr, arg2 int32, arg3 []byte, arg5 uintptr, ) int32 {" in normalized_source
    )
    assert (
        "return purego_func_fixture_bind_blob( arg1, arg2, arg3_ptr, uint64(len(arg3_len)), arg5, )"
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


def test_render_go_source_emits_callback_input_helper_functions() -> None:
    """Configured callback helpers should generate `purego.NewCallback` wrappers."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_register_hook",
                    result_c_type="int",
                    parameter_c_types=("fixture_ctx_t *", "int (*)(void *, int)", "void *"),
                    parameter_names=("ctx", "callback", "user_data"),
                    go_result_type="int32",
                    go_parameter_types=("uintptr", "uintptr", "uintptr"),
                ),
            ),
            typedefs=(
                TypedefDecl(name="fixture_ctx_t", c_type="struct fixture_ctx", go_type="uintptr"),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                RecordTypedefDecl(
                    name="fixture_ctx_t",
                    c_type="struct fixture_ctx",
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
        options=RenderOptions(
            helpers=GeneratorHelpers(
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_register_hook",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    normalized_source = " ".join(source.split())
    assert "func purego_func_fixture_register_hook_callbacks(" in source
    expected_signature = (
        "func purego_func_fixture_register_hook_callbacks("
        " ctx purego_type_fixture_ctx_t,"
        " callback func(uintptr, int32) int32,"
        " user_data uintptr, ) int32 {"
    )
    assert expected_signature in normalized_source
    assert "callback_callback := uintptr(0)" in source
    assert "if callback != nil {" in source
    assert "callback_callback = purego.NewCallback(callback)" in source
    assert (
        "return purego_func_fixture_register_hook( ctx, callback_callback, user_data, )"
        in normalized_source
    )


def test_render_go_source_emits_callback_input_helper_for_opaque_and_pointer_args() -> None:
    """Callback helper signatures should preserve opaque handles and raw pointer slots."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_create_function",
                    result_c_type="int",
                    parameter_c_types=(
                        "fixture_db_t *",
                        "void (*)(fixture_ctx_t *, int, fixture_value_t **)",
                    ),
                    parameter_names=("db", "callback"),
                    go_result_type="int32",
                    go_parameter_types=("uintptr", "uintptr"),
                ),
            ),
            typedefs=(
                TypedefDecl(name="fixture_db_t", c_type="struct fixture_db", go_type="uintptr"),
                TypedefDecl(name="fixture_ctx_t", c_type="struct fixture_ctx", go_type="uintptr"),
                TypedefDecl(
                    name="fixture_value_t",
                    c_type="struct fixture_value",
                    go_type="uintptr",
                ),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                RecordTypedefDecl(
                    name="fixture_db_t",
                    c_type="struct fixture_db",
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
                RecordTypedefDecl(
                    name="fixture_ctx_t",
                    c_type="struct fixture_ctx",
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
                RecordTypedefDecl(
                    name="fixture_value_t",
                    c_type="struct fixture_value",
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
        options=RenderOptions(
            helpers=GeneratorHelpers(
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_create_function",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    normalized_source = " ".join(source.split())
    assert "callback func(purego_type_fixture_ctx_t, int32, uintptr)" in normalized_source


def test_render_go_source_rejects_missing_callback_helper_function() -> None:
    """Callback-input helpers should fail when the target function is missing."""
    with pytest.raises(
        RendererError,
        match=r"callback helper target function not found: fixture_register_hook",
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
                    callback_inputs=(
                        CallbackInputHelper(
                            function="fixture_register_hook",
                            parameters=("callback",),
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_render_go_source_rejects_non_callback_callback_helper_parameter() -> None:
    """Callback-input helpers should reject non-function-pointer parameters."""
    with pytest.raises(
        RendererError,
        match=(
            r"callback helper fixture_register_hook parameter callback "
            r"must be a function pointer, got `int32_t`"
        ),
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fixture_register_hook",
                        result_c_type="int",
                        parameter_c_types=("int32_t",),
                        parameter_names=("callback",),
                        go_result_type="int32",
                        go_parameter_types=("int32",),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            options=RenderOptions(
                helpers=GeneratorHelpers(
                    callback_inputs=(
                        CallbackInputHelper(
                            function="fixture_register_hook",
                            parameters=("callback",),
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_render_go_source_rejects_missing_callback_helper_parameter() -> None:
    """Callback-input helpers should reject missing parameter names."""
    with pytest.raises(
        RendererError,
        match=r"callback helper fixture_register_hook parameter not found: callback",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fixture_register_hook",
                        result_c_type="int",
                        parameter_c_types=("void (*)(void)",),
                        parameter_names=("handler",),
                        go_result_type="int32",
                        go_parameter_types=("uintptr",),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            options=RenderOptions(
                helpers=GeneratorHelpers(
                    callback_inputs=(
                        CallbackInputHelper(
                            function="fixture_register_hook",
                            parameters=("callback",),
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )
