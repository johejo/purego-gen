# Copyright (c) 2026 purego-gen contributors.

"""Tests for Jinja2 renderer behavior."""

from __future__ import annotations

import pytest

from purego_gen.config_model import (
    CallbackInputHelper,
    GeneratorHelpers,
    GeneratorNaming,
    GeneratorRenderSpec,
)
from purego_gen.model import (
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
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
                "emit_kinds": ("func",),
                "has_func_or_var": True,
                "has_purego_import": True,
                "has_type_block": False,
                "has_gostring_util": False,
                "type_aliases": (),
                "func_type_aliases": (),
                "newcallback_helpers": (),
                "constants": (),
                "functions": ({"name": "add"},),
                "helpers": (),
                "owned_string_helpers": (),
                "runtime_vars": (),
                "register_functions_name": "purego_fixture_lib_register_functions",
                "load_runtime_vars_name": "purego_fixture_lib_load_runtime_vars",
                "gostring_func_name": "purego_gostring",
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


def test_render_go_source_uses_custom_identifier_prefix_everywhere() -> None:
    """Custom identifier prefixes should apply across all generated identifiers."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type", "const", "var"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="add",
                    result_c_type="int",
                    parameter_c_types=("int", "int"),
                    parameter_names=("lhs", "rhs"),
                    go_result_type="int32",
                    go_parameter_types=("int32", "int32"),
                ),
            ),
            typedefs=(TypedefDecl(name="fixture_mode_t", c_type="int", go_type="int32"),),
            constants=(ConstantDecl(name="FIXTURE_STATUS_OK", value=0),),
            runtime_vars=(RuntimeVarDecl(name="fixture_counter", c_type="int"),),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
            naming=GeneratorNaming(
                type_prefix="purego_gen_",
                const_prefix="purego_gen_",
                func_prefix="purego_gen_",
                var_prefix="purego_gen_",
            ),
        ),
    )

    assert "// C: int\n    purego_gen_type_fixture_mode_t = int32" in source
    assert "purego_gen_const_FIXTURE_STATUS_OK = 0" in source
    assert "purego_gen_func_add func(" in source
    assert "purego_gen_var_fixture_counter uintptr" in source
    assert "func purego_gen_fixture_lib_register_functions(handle uintptr) error {" in source
    assert "func purego_gen_fixture_lib_load_runtime_vars(handle uintptr) error {" in source


def test_render_go_source_allows_unprefixed_constants() -> None:
    """Constant names should be able to omit the generated namespace prefix."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("const",),
        declarations=ParsedDeclarations(
            functions=(),
            typedefs=(),
            constants=(
                ConstantDecl(name="SQLITE_OK", value=0),
                ConstantDecl(name="SQLITE_BUSY", value=5),
            ),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
            naming=GeneratorNaming(const_prefix=""),
        ),
    )

    assert "SQLITE_OK = 0" in source
    assert "SQLITE_BUSY = 5" in source


def test_render_go_source_generates_named_func_type_for_callback_params() -> None:
    """Non-typedef callback params should generate named func types and NewCallback helpers."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_register",
                    result_c_type="int",
                    parameter_c_types=("void (*)(int)",),
                    parameter_names=("on_event",),
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
                        function="fixture_register",
                        parameters=("on_event",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "purego_type_on_event_func = func(int32)" in source
    assert "func purego_new_on_event(fn purego_type_on_event_func) uintptr {" in source
    assert "return uintptr(purego.NewCallback(fn))" in source
    normalized_source = " ".join(source.split())
    assert "on_event purego_type_on_event_func," in normalized_source


def test_render_go_source_skips_named_func_type_for_typedef_backed_callback_params() -> None:
    """Typedef-backed callback params should not generate additional named types."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func", "type"),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_set_hook",
                    result_c_type="void",
                    parameter_c_types=("fixture_callback_t",),
                    parameter_names=("hook",),
                    go_result_type=None,
                    go_parameter_types=("uintptr",),
                ),
            ),
            typedefs=(
                TypedefDecl(
                    name="fixture_callback_t",
                    c_type="int (*)(int)",
                    go_type="uintptr",
                ),
            ),
            constants=(),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(
                callback_inputs=(
                    CallbackInputHelper(
                        function="fixture_set_hook",
                        parameters=("hook",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    # Typedef-derived types should exist
    assert "purego_type_fixture_callback_t_func = func(int32) int32" in source
    # No additional callback-param-derived type for "hook"
    assert "purego_type_hook_func" not in source


def test_render_go_source_qualifies_callback_param_names_on_signature_conflict() -> None:
    """Same param name with different signatures should get function-qualified names."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_fn_a",
                    result_c_type="void",
                    parameter_c_types=("int (*)(void *)",),
                    parameter_names=("handler",),
                    go_result_type=None,
                    go_parameter_types=("uintptr",),
                ),
                FunctionDecl(
                    name="fixture_fn_b",
                    result_c_type="void",
                    parameter_c_types=("void (*)(void *, int)",),
                    parameter_names=("handler",),
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
                        function="fixture_fn_a",
                        parameters=("handler",),
                    ),
                    CallbackInputHelper(
                        function="fixture_fn_b",
                        parameters=("handler",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    assert "purego_type_fixture_fn_a_handler_func = func(uintptr) int32" in source
    assert "purego_type_fixture_fn_b_handler_func = func(uintptr, int32)" in source
    assert "func purego_new_fixture_fn_a_handler(" in source
    assert "func purego_new_fixture_fn_b_handler(" in source
    # Simple name should NOT exist
    assert "purego_type_handler_func" not in source


def test_render_go_source_deduplicates_same_signature_callback_params() -> None:
    """Same param name with same signature across functions should generate one type."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="fixture_fn_a",
                    result_c_type="void",
                    parameter_c_types=("void (*)(int)",),
                    parameter_names=("on_done",),
                    go_result_type=None,
                    go_parameter_types=("uintptr",),
                ),
                FunctionDecl(
                    name="fixture_fn_b",
                    result_c_type="void",
                    parameter_c_types=("void (*)(int)",),
                    parameter_names=("on_done",),
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
                        function="fixture_fn_a",
                        parameters=("on_done",),
                    ),
                    CallbackInputHelper(
                        function="fixture_fn_b",
                        parameters=("on_done",),
                    ),
                )
            ),
            type_mapping=TypeMappingOptions(),
        ),
    )

    # Should generate one simple-named type, not qualified
    assert "purego_type_on_done_func = func(int32)" in source
    assert "func purego_new_on_done(fn purego_type_on_done_func) uintptr {" in source
    normalized_source = " ".join(source.split())
    assert "on_done purego_type_on_done_func," in normalized_source
    # Should NOT have qualified names
    assert "purego_type_fixture_fn_a_on_done_func" not in source
    assert "purego_type_fixture_fn_b_on_done_func" not in source
