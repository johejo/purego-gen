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
    OwnedStringReturnPatternHelper,
)
from purego_gen.helper_rendering import (
    detect_callback_registration_patterns,
    discover_callback_inputs,
    find_callback_candidates,
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


def test_render_go_source_callback_resolves_fixed_width_typedef_types() -> None:
    """Callback helpers should resolve fixed-width C typedefs (uint64_t, int32_t) in signatures."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_set_progress",
                    result_c_type="void",
                    parameter_c_types=("void (*)(uint64_t, int32_t)",),
                    parameter_names=("callback",),
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
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_set_progress",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "callback_func = func(uint64, int32)" in source


def test_render_go_source_callback_resolves_pointer_width_typedef_types() -> None:
    """Callback helpers should resolve uintptr_t/intptr_t to uintptr."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_set_visitor",
                    result_c_type="void",
                    parameter_c_types=("void (*)(uintptr_t, intptr_t)",),
                    parameter_names=("callback",),
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
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_set_visitor",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "callback_func = func(uintptr, uintptr)" in source


def test_render_go_source_callback_resolves_chained_typedef() -> None:
    """Callback helpers should chain-resolve library typedefs to underlying primitives."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_set_handler",
                    result_c_type="void",
                    parameter_c_types=("void (*)(idx_t, count_t)",),
                    parameter_names=("callback",),
                    go_result_type=None,
                    go_parameter_types=("uintptr",),
                ),
            ),
            typedefs=(
                TypedefDecl(name="idx_t", c_type="uint64_t", go_type="uint64"),
                TypedefDecl(name="count_t", c_type="int32_t", go_type="int32"),
            ),
            constants=(),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_set_handler",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "callback_func = func(uint64, int32)" in source


def test_render_go_source_callback_resolves_chained_typedef_through_go_type_lookup() -> None:
    """Callback helpers should chain-resolve typedefs through typedef_go_type_by_lookup."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_set_notifier",
                    result_c_type="void",
                    parameter_c_types=("void (*)(my_state_t)",),
                    parameter_names=("callback",),
                    go_result_type=None,
                    go_parameter_types=("uintptr",),
                ),
            ),
            typedefs=(
                TypedefDecl(name="state_t", c_type="int", go_type="int32"),
                TypedefDecl(name="my_state_t", c_type="state_t", go_type="int32"),
            ),
            constants=(),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_set_notifier",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "callback_func = func(int32)" in source


def test_render_go_source_callback_const_char_pointer_resolves_to_uintptr() -> None:
    """Callback helpers should resolve `const char *` parameters to uintptr."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_set_logger",
                    result_c_type="void",
                    parameter_c_types=("void (*)(const char *, int)",),
                    parameter_names=("callback",),
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
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_set_logger",
                        parameters=("callback",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "callback_func = func(uintptr, int32)" in source


def _make_declarations_with_callbacks() -> ParsedDeclarations:
    """Build declarations with callback and non-callback functions.

    Returns:
        Declarations with two callback functions and one plain function.
    """
    return ParsedDeclarations(
        functions=(
            FunctionDecl(
                name="fixture_register",
                result_c_type="int",
                parameter_c_types=("void (*)(int)",),
                parameter_names=("on_event",),
                go_result_type="int32",
                go_parameter_types=("uintptr",),
            ),
            FunctionDecl(
                name="fixture_notify",
                result_c_type="void",
                parameter_c_types=("void (*)(void)",),
                parameter_names=("on_done",),
                go_result_type=None,
                go_parameter_types=("uintptr",),
            ),
            FunctionDecl(
                name="plain_add",
                result_c_type="int",
                parameter_c_types=("int", "int"),
                parameter_names=("a", "b"),
                go_result_type="int32",
                go_parameter_types=("int32", "int32"),
            ),
        ),
        typedefs=(),
        constants=(),
        runtime_vars=(),
    )


def test_find_callback_candidates_discovers_function_pointer_params() -> None:
    """find_callback_candidates should return functions with function-pointer params."""
    declarations = _make_declarations_with_callbacks()
    candidates = find_callback_candidates(declarations)

    func_names = [name for name, _ in candidates]
    assert "fixture_register" in func_names
    assert "fixture_notify" in func_names
    assert "plain_add" not in func_names


def test_discover_callback_inputs_merges_with_explicit() -> None:
    """Explicit callback_inputs should take priority over auto-discovered ones."""
    declarations = _make_declarations_with_callbacks()
    explicit = (CallbackInputHelper(function="fixture_register", parameters=("on_event",)),)
    result = discover_callback_inputs(declarations, explicit_callback_inputs=explicit)

    func_names = [h.function for h in result]
    assert func_names == ["fixture_register", "fixture_notify"]
    # Explicit entry should be first (preserved), auto-discovered appended
    assert result[0].parameters == ("on_event",)


def test_discover_callback_inputs_skips_explicit_functions() -> None:
    """Auto-discovery should not duplicate functions already in explicit config."""
    declarations = _make_declarations_with_callbacks()
    explicit = (
        CallbackInputHelper(function="fixture_register", parameters=("on_event",)),
        CallbackInputHelper(function="fixture_notify", parameters=("on_done",)),
    )
    result = discover_callback_inputs(declarations, explicit_callback_inputs=explicit)

    assert result == explicit


def test_render_go_source_auto_callback_inputs_generates_helpers() -> None:
    """auto_callback_inputs=True should generate callback helpers for all candidates."""
    declarations = _make_declarations_with_callbacks()
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=declarations,
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(auto_callback_inputs=True),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "func fixture_register_callbacks(" in source
    assert "func fixture_notify_callbacks(" in source
    assert "on_event_func = func(int32)" in source
    assert "on_done_func = func()" in source


def test_detect_callback_registration_patterns_finds_destructor() -> None:
    """Pattern detection should find (callback, destructor) pairs by name heuristic."""
    declarations = ParsedDeclarations(
        functions=(
            FunctionDecl(
                name="register_with_destroy",
                result_c_type="void",
                parameter_c_types=(
                    "void (*)(int)",
                    "void *",
                    "void (*)(void *)",
                ),
                parameter_names=("callback", "user_data", "destroy"),
                go_result_type=None,
                go_parameter_types=("uintptr", "uintptr", "uintptr"),
            ),
        ),
        typedefs=(),
        constants=(),
        runtime_vars=(),
    )
    patterns = detect_callback_registration_patterns(declarations)

    assert len(patterns) >= 1
    pattern = next(p for p in patterns if p.callback_param == "callback")
    assert pattern.function == "register_with_destroy"
    assert pattern.userdata_param == "user_data"
    assert pattern.destructor_param == "destroy"


def test_detect_callback_registration_patterns_empty_for_plain_functions() -> None:
    """Pattern detection should return empty for functions without matching triples."""
    declarations = ParsedDeclarations(
        functions=(
            FunctionDecl(
                name="plain_add",
                result_c_type="int",
                parameter_c_types=("int", "int"),
                parameter_names=("a", "b"),
                go_result_type="int32",
                go_parameter_types=("int32", "int32"),
            ),
        ),
        typedefs=(),
        constants=(),
        runtime_vars=(),
    )
    patterns = detect_callback_registration_patterns(declarations)
    assert patterns == []


def _make_string_return_declarations() -> ParsedDeclarations:
    """Build declarations with several string-returning and non-string functions.

    Returns:
        Declarations with string-returning, non-string, and free functions.
    """
    return ParsedDeclarations(
        functions=(
            FunctionDecl(
                name="lib_get_name",
                result_c_type="const char *",
                parameter_c_types=("int",),
                parameter_names=("id",),
                go_result_type="string",
                go_parameter_types=("int32",),
            ),
            FunctionDecl(
                name="lib_get_label",
                result_c_type="const char *",
                parameter_c_types=(),
                parameter_names=(),
                go_result_type="string",
                go_parameter_types=(),
            ),
            FunctionDecl(
                name="lib_get_count",
                result_c_type="int",
                parameter_c_types=(),
                parameter_names=(),
                go_result_type="int32",
                go_parameter_types=(),
            ),
            FunctionDecl(
                name="lib_free",
                result_c_type="void",
                parameter_c_types=("void *",),
                parameter_names=("ptr",),
                go_result_type=None,
                go_parameter_types=("uintptr",),
            ),
            FunctionDecl(
                name="other_get_value",
                result_c_type="const char *",
                parameter_c_types=(),
                parameter_names=(),
                go_result_type="string",
                go_parameter_types=(),
            ),
        ),
        typedefs=(),
        constants=(),
        runtime_vars=(),
    )


def test_owned_string_pattern_matches_multiple_functions() -> None:
    """Pattern-based owned_string_returns should match multiple string-returning functions."""
    declarations = _make_string_return_declarations()
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=declarations,
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                owned_string_returns=(
                    OwnedStringReturnPatternHelper(
                        function_pattern="^lib_get_",
                        free_func="lib_free",
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "func lib_get_name_string(" in source
    assert "func lib_get_label_string(" in source
    # lib_get_count returns int32, not string — should be skipped
    assert "lib_get_count_string" not in source
    # other_get_value doesn't match the pattern
    assert "other_get_value_string" not in source


def test_owned_string_pattern_skips_non_string_return_types() -> None:
    """Pattern should silently skip functions whose return type is not string."""
    declarations = _make_string_return_declarations()
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=declarations,
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                owned_string_returns=(
                    OwnedStringReturnPatternHelper(
                        function_pattern="^lib_",
                        free_func="lib_free",
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "func lib_get_name_string(" in source
    assert "func lib_get_label_string(" in source
    assert "lib_get_count_string" not in source


def test_owned_string_pattern_zero_matches_raises_error() -> None:
    """Pattern that matches no string-returning functions should raise an error."""
    declarations = _make_string_return_declarations()
    with pytest.raises(
        RendererError,
        match=r"matched no string-returning functions",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=declarations,
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(
                    owned_string_returns=(
                        OwnedStringReturnPatternHelper(
                            function_pattern="^nonexistent_",
                            free_func="lib_free",
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_owned_string_pattern_deduplicates_with_explicit() -> None:
    """Explicit entries should take priority; patterns should skip those functions."""
    declarations = _make_string_return_declarations()
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=declarations,
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                owned_string_returns=(
                    OwnedStringReturnHelper(
                        function="lib_get_name",
                        free_func="lib_free",
                    ),
                    OwnedStringReturnPatternHelper(
                        function_pattern="^lib_get_",
                        free_func="lib_free",
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "func lib_get_name_string(" in source
    assert "func lib_get_label_string(" in source
    # lib_get_name should appear only once (from explicit, not duplicated by pattern)
    assert source.count("func lib_get_name_string(") == 1


def test_owned_string_pattern_invalid_regex_raises_error() -> None:
    """Invalid regex in function_pattern should raise an error."""
    declarations = _make_string_return_declarations()
    with pytest.raises(
        RendererError,
        match=r"not valid regex",
    ):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=declarations,
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(
                    owned_string_returns=(
                        OwnedStringReturnPatternHelper(
                            function_pattern="[invalid",
                            free_func="lib_free",
                        ),
                    )
                ),
                type_mapping=TypeMappingOptions(),
            ),
        )


def test_owned_string_pattern_deterministic_output_order() -> None:
    """Pattern matches should produce helpers in sorted (deterministic) order."""
    declarations = _make_string_return_declarations()
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=declarations,
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                owned_string_returns=(
                    OwnedStringReturnPatternHelper(
                        function_pattern="^lib_get_|^other_get_",
                        free_func="lib_free",
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    label_pos = source.index("func lib_get_label_string(")
    name_pos = source.index("func lib_get_name_string(")
    other_pos = source.index("func other_get_value_string(")
    assert label_pos < name_pos < other_pos
