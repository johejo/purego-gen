# Copyright (c) 2026 purego-gen contributors.

"""CLI diagnostics helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TextIO

from purego_gen.c_type_utils import extract_pointer_typedef_name
from purego_gen.diagnostic_codes import build_diagnostic_code

if TYPE_CHECKING:
    from purego_gen.model import ParsedDeclarations

OPAQUE_DIAGNOSTIC_CODE_EMITTED_COUNT: Final[str] = build_diagnostic_code(
    "OPAQUE",
    "EMITTED",
    "COUNT",
)
OPAQUE_DIAGNOSTIC_CODE_FALLBACK_COUNT: Final[str] = build_diagnostic_code(
    "OPAQUE",
    "FALLBACK",
    "UINTPTR",
    "COUNT",
)


def count_opaque_diagnostics(
    *,
    emit_kinds: tuple[str, ...],
    declarations: ParsedDeclarations,
) -> tuple[int, int]:
    """Count opaque-emission and fallback-to-uintptr diagnostics.

    Returns:
        Pair of emitted opaque typedef count and uintptr fallback slot count.
    """
    opaque_typedef_names = {
        record_typedef.name
        for record_typedef in declarations.record_typedefs
        if record_typedef.record_kind == "STRUCT_DECL" and record_typedef.is_opaque
    }
    emitted_opaque_typedef_names: set[str] = set()
    if "type" in emit_kinds:
        emitted_typedef_names = {typedef.name for typedef in declarations.typedefs}
        emitted_opaque_typedef_names = opaque_typedef_names.intersection(emitted_typedef_names)

    fallback_slot_count = 0
    if "func" in emit_kinds:
        for function in declarations.functions:
            function_slots: list[tuple[str, str]] = list(
                zip(function.go_parameter_types, function.parameter_c_types, strict=True)
            )
            if function.go_result_type is not None:
                function_slots.append((function.go_result_type, function.result_c_type))
            for go_type, c_type in function_slots:
                if go_type != "uintptr":
                    continue
                typedef_name = extract_pointer_typedef_name(c_type)
                if typedef_name is None or typedef_name not in opaque_typedef_names:
                    continue
                if typedef_name in emitted_opaque_typedef_names:
                    continue
                fallback_slot_count += 1
    return len(emitted_opaque_typedef_names), fallback_slot_count


def emit_generation_diagnostics(
    *,
    stream: TextIO,
    all_declarations: ParsedDeclarations,
    filtered_declarations: ParsedDeclarations,
    emit_kinds: tuple[str, ...],
) -> None:
    """Emit stable skipped/opaque diagnostics to stderr."""
    stream.writelines(
        (
            "purego-gen: skipped typedef "
            f"{skipped_typedef.name} ({skipped_typedef.c_type}) "
            f"[{skipped_typedef.reason_code}]: {skipped_typedef.reason}\n"
        )
        for skipped_typedef in all_declarations.skipped_typedefs
    )
    opaque_emitted_count, opaque_fallback_count = count_opaque_diagnostics(
        emit_kinds=emit_kinds,
        declarations=filtered_declarations,
    )
    stream.write(
        "purego-gen: opaque typedefs emitted "
        f"[{OPAQUE_DIAGNOSTIC_CODE_EMITTED_COUNT}]: {opaque_emitted_count}\n"
    )
    stream.write(
        "purego-gen: opaque function signature slots fell back to uintptr "
        f"[{OPAQUE_DIAGNOSTIC_CODE_FALLBACK_COUNT}]: {opaque_fallback_count}\n"
    )
