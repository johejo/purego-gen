# Copyright (c) 2026 purego-gen contributors.

"""CLI diagnostics helpers."""

from __future__ import annotations

from collections import Counter
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
INVENTORY_DIAGNOSTIC_CODE_EMITTED_FUNCTION_COUNT: Final[str] = build_diagnostic_code(
    "INVENTORY",
    "FUNCTION",
    "EMITTED",
    "COUNT",
)
INVENTORY_DIAGNOSTIC_CODE_EMITTED_TYPEDEF_COUNT: Final[str] = build_diagnostic_code(
    "INVENTORY",
    "TYPEDEF",
    "EMITTED",
    "COUNT",
)
INVENTORY_DIAGNOSTIC_CODE_EMITTED_CONSTANT_COUNT: Final[str] = build_diagnostic_code(
    "INVENTORY",
    "CONSTANT",
    "EMITTED",
    "COUNT",
)
INVENTORY_DIAGNOSTIC_CODE_EMITTED_RUNTIME_VAR_COUNT: Final[str] = build_diagnostic_code(
    "INVENTORY",
    "RUNTIME",
    "VAR",
    "EMITTED",
    "COUNT",
)
TYPE_DIAGNOSTIC_CODE_SKIPPED_COUNT: Final[str] = build_diagnostic_code(
    "TYPE",
    "SKIPPED",
    "COUNT",
)
_EMITTED_INVENTORY_COUNTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("func", "functions", INVENTORY_DIAGNOSTIC_CODE_EMITTED_FUNCTION_COUNT),
    ("type", "typedefs", INVENTORY_DIAGNOSTIC_CODE_EMITTED_TYPEDEF_COUNT),
    ("const", "constants", INVENTORY_DIAGNOSTIC_CODE_EMITTED_CONSTANT_COUNT),
    ("var", "runtime vars", INVENTORY_DIAGNOSTIC_CODE_EMITTED_RUNTIME_VAR_COUNT),
)


def _count_diagnostic_code(reason_code: str) -> str:
    """Build one stable count diagnostic code from a base reason code.

    Returns:
        Stable count diagnostic code derived from the input reason code.
    """
    return f"{reason_code}_COUNT"


def build_generation_inventory_lines(
    *,
    all_declarations: ParsedDeclarations,
    filtered_declarations: ParsedDeclarations,
    emit_kinds: tuple[str, ...],
) -> tuple[str, ...]:
    """Build stable inventory summary lines for generation diagnostics.

    Returns:
        Summary diagnostic lines in stable emission order.
    """
    emitted_counts = {
        "func": len(filtered_declarations.functions),
        "type": len(filtered_declarations.typedefs),
        "const": len(filtered_declarations.constants),
        "var": len(filtered_declarations.runtime_vars),
    }
    lines = [
        f"purego-gen: emitted {label} [{diagnostic_code}]: {emitted_counts[emit_kind]}\n"
        for emit_kind, label, diagnostic_code in _EMITTED_INVENTORY_COUNTS
        if emit_kind in emit_kinds
    ]
    lines.append(
        "purego-gen: skipped typedefs "
        f"[{TYPE_DIAGNOSTIC_CODE_SKIPPED_COUNT}]: {len(all_declarations.skipped_typedefs)}\n"
    )
    skipped_reason_counts = Counter(
        skipped_typedef.reason_code for skipped_typedef in all_declarations.skipped_typedefs
    )
    lines.extend(
        f"purego-gen: skipped typedefs [{_count_diagnostic_code(reason_code)}]: {count}\n"
        for reason_code, count in sorted(skipped_reason_counts.items())
    )
    return tuple(lines)


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
        build_generation_inventory_lines(
            all_declarations=all_declarations,
            filtered_declarations=filtered_declarations,
            emit_kinds=emit_kinds,
        )
    )
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
