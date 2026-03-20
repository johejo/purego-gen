# Copyright (c) 2026 purego-gen contributors.

"""Constant type/expression resolution and comment normalization."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from purego_gen.c_type_utils import normalize_c_type_for_lookup

if TYPE_CHECKING:
    from collections.abc import Mapping

    from purego_gen.model import TypeMappingOptions

_MAX_INT64: Final[int] = (1 << 63) - 1


def resolve_constant_type(*, value: int, type_mapping: TypeMappingOptions) -> str | None:
    """Resolve optional Go type annotation for one constant declaration.

    Returns:
        Go type name when strict sentinel typing applies, otherwise `None`.
    """
    if type_mapping.typed_sentinel_constants and value > _MAX_INT64:
        return "uint64"
    return None


def resolve_constant_expression(
    *,
    constant_expression: str | None,
    value: int,
    const_type: str | None,
) -> str:
    """Resolve emitted Go expression for one constant declaration.

    Returns:
        Go expression text used in the generated constant declaration.
    """
    if const_type is not None and constant_expression is not None:
        return constant_expression
    return str(value)


def resolve_typed_constant_type(
    *,
    constant_c_type: str | None,
    value: int,
    type_mapping: TypeMappingOptions,
    typedef_alias_type_by_lookup: Mapping[str, str],
    typedef_go_type_by_lookup: Mapping[str, str],
) -> str | None:
    """Resolve optional Go type annotation for one constant declaration.

    Returns:
        Go type text for typed constant emission, or `None` when the constant
        should stay untyped.
    """
    if type_mapping.typed_sentinel_constants and constant_c_type is not None:
        alias_type = typedef_alias_type_by_lookup.get(constant_c_type)
        if alias_type is not None:
            return alias_type
        normalized_c_type = normalize_c_type_for_lookup(constant_c_type)
        alias_type = typedef_alias_type_by_lookup.get(normalized_c_type)
        if alias_type is not None:
            return alias_type
        go_type = typedef_go_type_by_lookup.get(constant_c_type)
        if go_type is not None:
            return go_type
        go_type = typedef_go_type_by_lookup.get(normalized_c_type)
        if go_type is not None:
            return go_type
    return resolve_constant_type(value=value, type_mapping=type_mapping)


def trim_comment_blank_edges(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Trim leading/trailing empty lines from normalized comment lines.

    Returns:
        Comment lines without outer blank lines.
    """
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return lines[start:end]


def normalize_comment_lines(comment: str | None) -> tuple[str, ...]:
    """Normalize libclang raw comment text into Go `//` body lines.

    Returns:
        Comment lines suitable for rendering as `// {line}`.
    """
    if comment is None:
        return ()

    normalized = comment.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ()

    is_block = normalized.startswith("/*") and normalized.endswith("*/")
    processed: list[str] = []

    if is_block:
        block_body = normalized[2:-2]
        for line in block_body.split("\n"):
            stripped_line = re.sub(r"^\s*\* ?", "", line)
            processed.append(stripped_line.strip())
        return trim_comment_blank_edges(tuple(processed))

    for line in normalized.split("\n"):
        stripped_line = re.sub(r"^\s*/// ?", "", line)
        stripped_line = re.sub(r"^\s*// ?", "", stripped_line)
        processed.append(stripped_line.strip())
    return trim_comment_blank_edges(tuple(processed))
