# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, DOC501

"""Identifier normalization helpers shared by parser/renderer/CLI layers."""

from __future__ import annotations

import re
from typing import Final

GO_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GO_KEYWORDS: Final[frozenset[str]] = frozenset({
    "break",
    "case",
    "chan",
    "const",
    "continue",
    "default",
    "defer",
    "else",
    "fallthrough",
    "for",
    "func",
    "go",
    "goto",
    "if",
    "import",
    "interface",
    "map",
    "package",
    "range",
    "return",
    "select",
    "struct",
    "switch",
    "type",
    "var",
})


def is_go_identifier(value: str) -> bool:
    """Check whether one token is a valid Go identifier."""
    return GO_IDENTIFIER_PATTERN.fullmatch(value) is not None


def sanitize_identifier(
    raw: str,
    *,
    fallback: str,
    digit_prefix: str,
    strip_outer_underscores: bool,
) -> str:
    """Normalize arbitrary text into one Go identifier token."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", raw)
    if strip_outer_underscores:
        normalized = normalized.strip("_")
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"{digit_prefix}{normalized}"
    if normalized in GO_KEYWORDS:
        normalized = f"{normalized}_"
    return normalized


def sanitize_struct_field_identifier(raw: str, *, fallback: str) -> str:
    """Normalize struct-field names for parser struct literal emission."""
    return sanitize_identifier(
        raw,
        fallback=fallback,
        digit_prefix="f_",
        strip_outer_underscores=True,
    )


def sanitize_symbol_suffix(raw: str, *, fallback: str) -> str:
    """Normalize generated declaration suffix preserving source casing."""
    return sanitize_identifier(
        raw,
        fallback=fallback,
        digit_prefix="n_",
        strip_outer_underscores=False,
    )


def allocate_unique_identifier(base_identifier: str, *, seen: set[str]) -> str:
    """Allocate a deterministic unique identifier in one category."""
    if base_identifier not in seen:
        seen.add(base_identifier)
        return base_identifier

    suffix = 2
    while f"{base_identifier}_{suffix}" in seen:
        suffix += 1
    resolved = f"{base_identifier}_{suffix}"
    seen.add(resolved)
    return resolved


def build_unique_identifiers(
    raw_names: tuple[str, ...],
    *,
    fallback_prefix: str,
) -> tuple[str, ...]:
    """Build deterministic unique identifiers for one declaration category."""
    seen: set[str] = set()
    resolved: list[str] = []
    for index, raw_name in enumerate(raw_names, start=1):
        base_identifier = sanitize_symbol_suffix(raw_name, fallback=f"{fallback_prefix}_{index}")
        resolved.append(allocate_unique_identifier(base_identifier, seen=seen))
    return tuple(resolved)


def normalize_lib_id(value: str) -> str:
    """Normalize library id text to snake_case-safe identifier."""
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    if not normalized:
        message = "--lib-id must contain at least one alphanumeric character."
        raise ValueError(message)
    if normalized[0].isdigit():
        normalized = f"lib_{normalized}"
    return normalized
