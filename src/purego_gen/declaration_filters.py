# Copyright (c) 2026 purego-gen contributors.

"""Shared declaration-filter compilation and application helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from purego_gen.model import ParsedDeclarations

if TYPE_CHECKING:
    from collections.abc import Callable

FILTER_KIND_REGEX: Final[str] = "regex"
FILTER_KIND_EXACT_NAMES: Final[str] = "exact_names"


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """One declaration filter expressed as regex or exact-name list."""

    kind: str
    regex: str | None = None
    exact_names: tuple[str, ...] = ()

    @property
    def regex_pattern(self) -> str:
        """Return a regex pattern string for matching declarations.

        Raises:
            ValueError: Filter spec is internally inconsistent.
        """
        if self.kind == FILTER_KIND_REGEX:
            if self.regex is None:
                message = "regex filter requires a regex pattern."
                raise ValueError(message)
            return self.regex
        if self.kind == FILTER_KIND_EXACT_NAMES:
            return build_exact_symbol_regex(self.exact_names)
        message = f"unsupported filter kind: {self.kind}"
        raise ValueError(message)

    @property
    def display_value(self) -> str:
        """Return the user-facing filter value for diagnostics.

        Raises:
            ValueError: Filter spec is internally inconsistent.
        """
        if self.kind == FILTER_KIND_REGEX:
            if self.regex is None:
                message = "regex filter requires a regex pattern."
                raise ValueError(message)
            return self.regex
        if self.kind == FILTER_KIND_EXACT_NAMES:
            return json.dumps(list(self.exact_names))
        message = f"unsupported filter kind: {self.kind}"
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class CompiledDeclarationFilters:
    """Compiled declaration regex filters."""

    func: re.Pattern[str] | None
    type_: re.Pattern[str] | None
    const: re.Pattern[str] | None
    var: re.Pattern[str] | None
    func_exclude: re.Pattern[str] | None = None
    type_exclude: re.Pattern[str] | None = None
    const_exclude: re.Pattern[str] | None = None
    var_exclude: re.Pattern[str] | None = None


def build_exact_symbol_regex(symbols: tuple[str, ...]) -> str:
    """Build an exact-match regex that matches only the provided symbols.

    Returns:
        Regular expression string matching exactly the provided symbols.
    """
    escaped = [re.escape(symbol) for symbol in symbols]
    return "^(" + "|".join(escaped) + ")$"


def regex_filter(pattern: str) -> FilterSpec:
    """Build one regex-backed filter spec.

    Returns:
        Filter spec that preserves the regex pattern verbatim.
    """
    return FilterSpec(kind=FILTER_KIND_REGEX, regex=pattern)


def exact_names_filter(names: tuple[str, ...]) -> FilterSpec:
    """Build one exact-name filter spec.

    Returns:
        Filter spec that matches only the provided declaration names.
    """
    return FilterSpec(kind=FILTER_KIND_EXACT_NAMES, exact_names=names)


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


def compile_filter_spec(
    spec: FilterSpec | None,
    *,
    option_name: str,
) -> re.Pattern[str] | None:
    """Compile one optional filter spec into a regex pattern.

    Returns:
        Compiled regular expression when provided, otherwise `None`.
    """
    if spec is None:
        return None
    return compile_filter(spec.regex_pattern, option_name=option_name)


def _apply_one_filter_pair[DeclarationT](
    declarations: tuple[DeclarationT, ...],
    *,
    include_filter: re.Pattern[str] | None,
    exclude_filter: re.Pattern[str] | None,
    name_getter: Callable[[DeclarationT], str],
) -> tuple[DeclarationT, ...]:
    """Apply one include/exclude filter pair while preserving input order.

    Returns:
        Filtered declarations after include/exclude matching.
    """
    filtered = declarations
    if include_filter is not None:
        filtered = tuple(
            declaration
            for declaration in filtered
            if include_filter.search(name_getter(declaration))
        )
    if exclude_filter is not None:
        filtered = tuple(
            declaration
            for declaration in filtered
            if not exclude_filter.search(name_getter(declaration))
        )
    return filtered


def apply_declaration_filters(
    declarations: ParsedDeclarations,
    *,
    filters: CompiledDeclarationFilters,
) -> ParsedDeclarations:
    """Apply category-specific filters to parsed declarations.

    Returns:
        Filtered declaration payload.
    """
    functions = _apply_one_filter_pair(
        declarations.functions,
        include_filter=filters.func,
        exclude_filter=filters.func_exclude,
        name_getter=lambda declaration: declaration.name,
    )
    typedefs = _apply_one_filter_pair(
        declarations.typedefs,
        include_filter=filters.type_,
        exclude_filter=filters.type_exclude,
        name_getter=lambda declaration: declaration.name,
    )
    record_typedefs = _apply_one_filter_pair(
        declarations.record_typedefs,
        include_filter=filters.type_,
        exclude_filter=filters.type_exclude,
        name_getter=lambda declaration: declaration.name,
    )
    constants = _apply_one_filter_pair(
        declarations.constants,
        include_filter=filters.const,
        exclude_filter=filters.const_exclude,
        name_getter=lambda declaration: declaration.name,
    )
    runtime_vars = _apply_one_filter_pair(
        declarations.runtime_vars,
        include_filter=filters.var,
        exclude_filter=filters.var_exclude,
        name_getter=lambda declaration: declaration.name,
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
    option_value: FilterSpec | None,
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
    message = f"no declarations matched {option_name}: {option_value.display_value}"
    raise ValueError(message)
