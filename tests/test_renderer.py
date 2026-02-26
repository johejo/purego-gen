# Copyright (c) 2026 purego-gen contributors.

"""Tests for Jinja2 renderer behavior."""

from __future__ import annotations

import pytest

from purego_gen.model import (
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
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
                    go_result_type=None,
                    go_parameter_types=(),
                ),
                FunctionDecl(
                    name="dup_name",
                    result_c_type="void",
                    parameter_c_types=(),
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
