# Copyright (c) 2026 purego-gen contributors.

"""Tests for helper rendering and helper-specific validation."""

from __future__ import annotations

import pytest

from purego_gen.config_model import (
    BufferInputHelper,
    BufferInputPair,
    CallbackInputHelper,
    GeneratorHelpers,
    GeneratorNaming,
    GeneratorRenderSpec,
)
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_OPAQUE_INCOMPLETE_STRUCT,
    FunctionDecl,
    ParsedDeclarations,
    RecordTypedefDecl,
    TypedefDecl,
    TypeMappingOptions,
)
from purego_gen.renderer import RendererError, render_go_source

_FIXTURE_PACKAGE = "fixture"
_FIXTURE_LIB_ID = "fixture_lib"


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
        render=GeneratorRenderSpec(
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


def test_render_go_source_emits_helpers_with_custom_identifier_prefix() -> None:
    """Helper wrappers should follow the configured identifier prefix."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_consume_bytes",
                    result_c_type="int",
                    parameter_c_types=("const void *", "size_t"),
                    parameter_names=("data", "data_len"),
                    go_result_type="int32",
                    go_parameter_types=("uintptr", "uint64"),
                ),
            ),
            typedefs=(),
            constants=(),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                buffer_inputs=(
                    BufferInputHelper(
                        function="fixture_consume_bytes",
                        pairs=(BufferInputPair(pointer="data", length="data_len"),),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
            naming=GeneratorNaming(identifier_prefix="purego_gen_"),
        ),
    )

    assert "func purego_gen_func_fixture_consume_bytes_bytes(" in source
    assert "return purego_gen_func_fixture_consume_bytes(" in source


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
        render=GeneratorRenderSpec(
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
            render=GeneratorRenderSpec(
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
            render=GeneratorRenderSpec(
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
        render=GeneratorRenderSpec(
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
        render=GeneratorRenderSpec(
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
            render=GeneratorRenderSpec(
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
            render=GeneratorRenderSpec(
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
            render=GeneratorRenderSpec(
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
