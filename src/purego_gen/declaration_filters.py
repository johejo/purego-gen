# Copyright (c) 2026 purego-gen contributors.

"""Shared declaration-filter compilation and application helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from purego_gen.model import ParsedDeclarations


@dataclass(frozen=True, slots=True)
class CompiledDeclarationFilters:
    """Compiled declaration regex filters."""

    func: re.Pattern[str] | None
    type_: re.Pattern[str] | None
    const: re.Pattern[str] | None
    var: re.Pattern[str] | None


def compile_filter(pattern: str | None, *, option_name: str) -> re.Pattern[str] | None:
    """Compile one optional regex filter.

    Returns:
        Compiled regular expression when provided, otherwise `None`.

    Raises:
        ValueError: Regex compilation fails.
    """
    if pattern is None:
        return None
    try:
        return re.compile(pattern)
    except re.error as error:
        message = f"invalid {option_name} regex: {error}"
        raise ValueError(message) from error


def apply_declaration_filters(
    declarations: ParsedDeclarations,
    *,
    filters: CompiledDeclarationFilters,
) -> ParsedDeclarations:
    """Apply category-specific filters to parsed declarations.

    Returns:
        Filtered declaration payload.
    """
    functions = declarations.functions
    if filters.func is not None:
        functions = tuple(function for function in functions if filters.func.search(function.name))

    typedefs = declarations.typedefs
    if filters.type_ is not None:
        typedefs = tuple(typedef for typedef in typedefs if filters.type_.search(typedef.name))

    record_typedefs = declarations.record_typedefs
    if filters.type_ is not None:
        record_typedefs = tuple(
            record_typedef
            for record_typedef in record_typedefs
            if filters.type_.search(record_typedef.name)
        )

    constants = declarations.constants
    if filters.const is not None:
        constants = tuple(constant for constant in constants if filters.const.search(constant.name))

    runtime_vars = declarations.runtime_vars
    if filters.var is not None:
        runtime_vars = tuple(
            runtime_var for runtime_var in runtime_vars if filters.var.search(runtime_var.name)
        )

    return ParsedDeclarations(
        functions=functions,
        typedefs=typedefs,
        constants=constants,
        runtime_vars=runtime_vars,
        skipped_typedefs=declarations.skipped_typedefs,
        record_typedefs=record_typedefs,
    )


def validate_filter_match(
    *,
    emit_kinds: tuple[str, ...],
    option_value: str | None,
    option_name: str,
    emit_kind: str,
    has_match: bool,
) -> None:
    """Ensure configured filter matches at least one declaration.

    Raises:
        ValueError: Configured filter matches no declarations in the enabled category.
    """
    if option_value is None or emit_kind not in emit_kinds or has_match:
        return
    message = f"no declarations matched {option_name}: {option_value}"
    raise ValueError(message)
