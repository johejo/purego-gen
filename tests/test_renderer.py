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
    RecordFieldDecl,
    RecordTypedefDecl,
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
                "struct_accessors": (),
                "runtime_vars": (),
                "register_functions_name": "fixture_lib_register_functions",
                "load_runtime_vars_name": "fixture_lib_load_runtime_vars",
                "gostring_func_name": "gostring",
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
    assert "dup_name func()" in source
    assert "dup_name_2 func()" in source
    assert "FOO_BAR = 1" in source
    assert "FOO_BAR_2 = 2" in source


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
    assert "fixture_callback_t_func = func(int32) int32" in source
    # No additional callback-param-derived type for "hook"
    assert "\n    hook_func" not in source


def test_render_go_source_prefix_free_errors_on_predeclared_collision() -> None:
    """Prefix-free naming should error when a generated name shadows a Go predeclared identifier."""
    with pytest.raises(RendererError, match="predeclared"):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func",),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="string",
                        result_c_type="int",
                        parameter_c_types=(),
                        parameter_names=(),
                        go_result_type="int32",
                        go_parameter_types=(),
                    ),
                ),
                typedefs=(),
                constants=(),
                runtime_vars=(),
            ),
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(),
                type_mapping=TypeMappingOptions(),
                naming=GeneratorNaming(
                    type_prefix="",
                    const_prefix="",
                    func_prefix="",
                    var_prefix="",
                ),
            ),
        )


def test_render_go_source_prefix_free_errors_on_cross_category_collision() -> None:
    """Prefix-free naming should error when names collide across categories."""
    with pytest.raises(RendererError, match="collides with"):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func", "const"),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="status",
                        result_c_type="int",
                        parameter_c_types=(),
                        parameter_names=(),
                        go_result_type="int32",
                        go_parameter_types=(),
                    ),
                ),
                typedefs=(),
                constants=(ConstantDecl(name="status", value=0),),
                runtime_vars=(),
            ),
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(),
                type_mapping=TypeMappingOptions(),
                naming=GeneratorNaming(
                    type_prefix="",
                    const_prefix="",
                    func_prefix="",
                    var_prefix="",
                ),
            ),
        )


def test_render_go_source_const_prefix_empty_does_not_check_predeclared() -> None:
    """Existing const_prefix='' feature should not regress with reserved-name validation."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("const",),
        declarations=ParsedDeclarations(
            functions=(),
            typedefs=(),
            constants=(ConstantDecl(name="string", value=42),),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
            naming=GeneratorNaming(
                type_prefix="pfx_",
                const_prefix="",
                func_prefix="pfx_",
                var_prefix="pfx_",
            ),
        ),
    )

    assert "string = 42" in source


def test_render_go_source_partial_empty_prefix_validates_only_empty_categories() -> None:
    """Only categories with empty prefix should be checked for reserved-name issues."""
    with pytest.raises(RendererError, match="import name"):
        render_go_source(
            package=_FIXTURE_PACKAGE,
            lib_id=_FIXTURE_LIB_ID,
            emit_kinds=("func", "type"),
            declarations=ParsedDeclarations(
                functions=(
                    FunctionDecl(
                        name="fmt",
                        result_c_type="void",
                        parameter_c_types=(),
                        parameter_names=(),
                        go_result_type=None,
                        go_parameter_types=(),
                    ),
                ),
                typedefs=(TypedefDecl(name="string", c_type="char *", go_type="uintptr"),),
                constants=(),
                runtime_vars=(),
            ),
            render=GeneratorRenderSpec(
                helpers=GeneratorHelpers(),
                type_mapping=TypeMappingOptions(),
                naming=GeneratorNaming(
                    type_prefix="pfx_",
                    func_prefix="",
                ),
            ),
        )


def test_render_go_source_skips_validation_when_all_prefixes_set() -> None:
    """No validation overhead when all prefixes are non-empty."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("func",),
        declarations=ParsedDeclarations(
            functions=(
                FunctionDecl(
                    name="string",
                    result_c_type="int",
                    parameter_c_types=(),
                    parameter_names=(),
                    go_result_type="int32",
                    go_parameter_types=(),
                ),
            ),
            typedefs=(),
            constants=(),
            runtime_vars=(),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
            naming=GeneratorNaming(
                type_prefix="pfx_",
                const_prefix="pfx_",
                func_prefix="pfx_",
                var_prefix="pfx_",
            ),
        ),
    )

    assert "pfx_string func(" in source


def _make_record_typedef(
    name: str,
    fields: tuple[RecordFieldDecl, ...],
) -> RecordTypedefDecl:
    return RecordTypedefDecl(
        name=name,
        c_type=f"struct {name}",
        record_kind="STRUCT_DECL",
        size_bytes=8,
        align_bytes=4,
        fields=fields,
        supported=True,
        unsupported_code=None,
        unsupported_reason=None,
    )


def _make_supported_field(name: str, c_type: str, go_name: str, go_type: str) -> RecordFieldDecl:
    return RecordFieldDecl(
        name=name,
        c_type=c_type,
        kind="FIELD_DECL",
        offset_bits=0,
        size_bytes=4,
        align_bytes=4,
        is_bitfield=False,
        bitfield_width=None,
        supported=True,
        unsupported_code=None,
        unsupported_reason=None,
        go_name=go_name,
        go_type=go_type,
    )


def test_render_go_source_struct_accessors_disabled_by_default() -> None:
    """struct_accessors should not generate methods when disabled (default)."""
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("type",),
        declarations=ParsedDeclarations(
            functions=(),
            typedefs=(
                TypedefDecl(
                    name="my_struct",
                    c_type="struct {\n\tint32 year;\n}",
                    go_type="struct {\n\tyear int32\n}",
                ),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                _make_record_typedef(
                    "my_struct",
                    fields=(_make_supported_field("year", "int32_t", "year", "int32"),),
                ),
            ),
        ),
    )

    assert "Get_year()" not in source
    assert "Set_year(" not in source


def test_render_go_source_struct_accessors_skips_unsupported_fields() -> None:
    """Unsupported fields (go_name=None) should not generate accessors."""
    unsupported_field = RecordFieldDecl(
        name="bitfield",
        c_type="unsigned int",
        kind="FIELD_DECL",
        offset_bits=0,
        size_bytes=4,
        align_bytes=4,
        is_bitfield=True,
        bitfield_width=3,
        supported=False,
        unsupported_code="unsupported_bitfield",
        unsupported_reason="bitfield not supported",
        go_name=None,
        go_type=None,
    )
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("type",),
        declarations=ParsedDeclarations(
            functions=(),
            typedefs=(
                TypedefDecl(
                    name="my_struct",
                    c_type="struct {\n\tint32 year;\n}",
                    go_type="struct {\n\tyear int32\n}",
                ),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                _make_record_typedef(
                    "my_struct",
                    fields=(
                        _make_supported_field("year", "int32_t", "year", "int32"),
                        unsupported_field,
                    ),
                ),
            ),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
            struct_accessors=True,
        ),
    )

    assert "Get_year()" in source
    assert "Get_bitfield()" not in source


def test_render_go_source_struct_accessors_skips_nested_struct_fields() -> None:
    """Fields with anonymous struct types (multiline go_type) should not generate accessors."""
    nested_field = _make_supported_field(
        "date",
        "duckdb_date_struct",
        "date",
        "struct {\n\tyear  int32\n\tmonth int8\n\tday   int8\n\t_     [2]byte\n}",
    )
    source = render_go_source(
        package=_FIXTURE_PACKAGE,
        lib_id=_FIXTURE_LIB_ID,
        emit_kinds=("type",),
        declarations=ParsedDeclarations(
            functions=(),
            typedefs=(
                TypedefDecl(
                    name="my_ts",
                    c_type="struct {\n\tduckdb_date_struct date;\n\tint32 micros;\n}",
                    go_type="struct {\n\tdate struct { ... }\n\tmicros int32\n}",
                ),
            ),
            constants=(),
            runtime_vars=(),
            record_typedefs=(
                _make_record_typedef(
                    "my_ts",
                    fields=(
                        nested_field,
                        _make_supported_field("micros", "int32_t", "micros", "int32"),
                    ),
                ),
            ),
        ),
        render=GeneratorRenderSpec(
            helpers=GeneratorHelpers(),
            type_mapping=TypeMappingOptions(),
            struct_accessors=True,
        ),
    )

    assert "Get_date()" not in source
    assert "Get_micros()" in source
