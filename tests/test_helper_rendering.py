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
    OwnedStringReturnHelper,
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
            naming=GeneratorNaming(
                type_prefix="purego_gen_",
                const_prefix="purego_gen_",
                func_prefix="purego_gen_",
                var_prefix="purego_gen_",
            ),
        ),
    )

    assert "func purego_gen_fixture_consume_bytes_bytes(" in source
    assert "return purego_gen_fixture_consume_bytes(" in source


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
    assert "func fixture_bind_blob_bytes(" in source
    assert (
        "func fixture_bind_blob_bytes("
        " arg1 uintptr, arg2 int32, arg3 []byte, arg5 func(uintptr), ) int32 {" in normalized_source
    )
    assert (
        "return fixture_bind_blob( arg1, arg2, arg3_ptr, uint64(len(arg3_len)), arg5, )"
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
                TypedefDecl(name="fixture_ctx_t", c_type="struct fixture_ctx", go_type="struct{}"),
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
    assert "func fixture_register_hook_callbacks(" in source
    expected_signature = (
        "func fixture_register_hook_callbacks("
        " ctx *fixture_ctx_t,"
        " callback callback_func,"
        " user_data uintptr, ) int32 {"
    )
    assert expected_signature in normalized_source
    assert "callback_func = func(uintptr, int32) int32" in source
    assert "func new_callback(fn callback_func) uintptr {" in source
    assert "callback_callback := uintptr(0)" in source
    assert "if callback != nil {" in source
    assert "callback_callback = purego.NewCallback(callback)" in source
    assert "return fixture_register_hook( ctx, callback_callback, user_data, )" in normalized_source


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
                TypedefDecl(name="fixture_db_t", c_type="struct fixture_db", go_type="struct{}"),
                TypedefDecl(name="fixture_ctx_t", c_type="struct fixture_ctx", go_type="struct{}"),
                TypedefDecl(
                    name="fixture_value_t",
                    c_type="struct fixture_value",
                    go_type="struct{}",
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
    assert "callback callback_func," in normalized_source
    assert "callback_func = func(*fixture_ctx_t, int32, **fixture_value_t)" in normalized_source


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


def test_render_go_source_rejects_missing_owned_string_return_function() -> None:
    """Owned-string-return helpers should fail when the target function is missing."""
    with pytest.raises(
        RendererError,
        match=r"owned_string_returns helper target function not found: fixture_get_name",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fixture_free",
                        result_c_type="void",
                        parameter_c_types=("void *",),
                        parameter_names=("ptr",),
                        go_result_type=None,
                        go_parameter_types=("uintptr",),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(
                    owned_string_returns=(
                        OwnedStringReturnHelper(
                            function="fixture_get_name",
                            free_func="fixture_free",
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_render_go_source_rejects_non_string_owned_string_return() -> None:
    """Owned-string-return helpers should reject functions that do not return string."""
    with pytest.raises(
        RendererError,
        match=r"must return string, got `int32`",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fixture_get_id",
                        result_c_type="int",
                        parameter_c_types=(),
                        parameter_names=(),
                        go_result_type="int32",
                        go_parameter_types=(),
                    ),
                    FunctionDecl(
                        name="fixture_free",
                        result_c_type="void",
                        parameter_c_types=("void *",),
                        parameter_names=("ptr",),
                        go_result_type=None,
                        go_parameter_types=("uintptr",),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(
                    owned_string_returns=(
                        OwnedStringReturnHelper(
                            function="fixture_get_id",
                            free_func="fixture_free",
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_render_go_source_rejects_missing_owned_string_return_free_func() -> None:
    """Owned-string-return helpers should fail when the free function is missing."""
    with pytest.raises(
        RendererError,
        match=r"owned_string_returns helper free function not found: fixture_free",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fixture_get_name",
                        result_c_type="const char *",
                        parameter_c_types=("int",),
                        parameter_names=("id",),
                        go_result_type="string",
                        go_parameter_types=("int32",),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(
                    owned_string_returns=(
                        OwnedStringReturnHelper(
                            function="fixture_get_name",
                            free_func="fixture_free",
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_render_go_source_emits_owned_string_return_with_custom_prefix() -> None:
    """Owned-string-return helpers should follow the configured identifier prefix."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_get_name",
                    result_c_type="const char *",
                    parameter_c_types=("int",),
                    parameter_names=("id",),
                    go_result_type="string",
                    go_parameter_types=("int32",),
                ),
                FunctionDecl(
                    name="fixture_free",
                    result_c_type="void",
                    parameter_c_types=("void *",),
                    parameter_names=("ptr",),
                    go_result_type=None,
                    go_parameter_types=("uintptr",),
                ),
            ),
            typedefs=(),
            constants=(),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                owned_string_returns=(
                    OwnedStringReturnHelper(
                        function="fixture_get_name",
                        free_func="fixture_free",
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
            naming=GeneratorNaming(
                type_prefix="mylib_",
                const_prefix="mylib_",
                func_prefix="mylib_",
                var_prefix="mylib_",
            ),
        ),
    )

    assert "func mylib_fixture_get_name_string(" in source
    assert "func mylib_gostring(ptr uintptr) string {" in source
    assert "result := mylib_gostring(rawPtr)" in source
