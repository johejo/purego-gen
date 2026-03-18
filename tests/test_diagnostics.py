# Copyright (c) 2026 purego-gen contributors.

"""Tests for generation diagnostics helpers."""

from __future__ import annotations

from purego_gen.diagnostics import (
    INVENTORY_DIAGNOSTIC_CODE_EMITTED_CONSTANT_COUNT,
    INVENTORY_DIAGNOSTIC_CODE_EMITTED_FUNCTION_COUNT,
    TYPE_DIAGNOSTIC_CODE_SKIPPED_COUNT,
    build_generation_inventory_lines,
)
from purego_gen.model import (
    ConstantDecl,
    FunctionDecl,
    ParsedDeclarations,
    SkippedTypedefDecl,
)


def test_build_generation_inventory_lines_groups_skipped_typedefs_by_reason() -> None:
    """Inventory summary should count emitted declarations and skipped typedef reasons."""
    all_declarations = ParsedDeclarations(
        functions=(),
        typedefs=(),
        constants=(),
        runtime_vars=(),
        skipped_typedefs=(
            SkippedTypedefDecl(
                name="fixture_union_t",
                c_type="union fixture_union",
                reason_code="PUREGO_GEN_TYPE_UNSUPPORTED_UNION_TYPEDEF",
                reason="union typedefs are not supported in v1",
            ),
            SkippedTypedefDecl(
                name="fixture_with_bitfield_t",
                c_type="struct fixture_with_bitfield",
                reason_code="PUREGO_GEN_TYPE_UNSUPPORTED_BITFIELD",
                reason="bitfield flags is not supported in v1",
            ),
            SkippedTypedefDecl(
                name="fixture_other_union_t",
                c_type="union fixture_other_union",
                reason_code="PUREGO_GEN_TYPE_UNSUPPORTED_UNION_TYPEDEF",
                reason="union typedefs are not supported in v1",
            ),
        ),
    )
    filtered_declarations = ParsedDeclarations(
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
        typedefs=(),
        constants=(ConstantDecl(name="FIXTURE_STATUS_OK", value=0),),
        runtime_vars=(),
    )

    lines = build_generation_inventory_lines(
        all_declarations=all_declarations,
        filtered_declarations=filtered_declarations,
        emit_kinds=("func", "const"),
    )

    assert lines == (
        f"purego-gen: emitted functions [{INVENTORY_DIAGNOSTIC_CODE_EMITTED_FUNCTION_COUNT}]: 1\n",
        f"purego-gen: emitted constants [{INVENTORY_DIAGNOSTIC_CODE_EMITTED_CONSTANT_COUNT}]: 1\n",
        f"purego-gen: skipped typedefs [{TYPE_DIAGNOSTIC_CODE_SKIPPED_COUNT}]: 3\n",
        "purego-gen: skipped typedefs [PUREGO_GEN_TYPE_UNSUPPORTED_BITFIELD_COUNT]: 1\n",
        "purego-gen: skipped typedefs [PUREGO_GEN_TYPE_UNSUPPORTED_UNION_TYPEDEF_COUNT]: 2\n",
    )
