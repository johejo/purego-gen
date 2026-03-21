# Copyright (c) 2026 purego-gen contributors.

"""Identifier normalization helpers shared by parser/renderer/CLI layers."""

from __future__ import annotations

import re
from typing import Final

GO_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GO_PREDECLARED: Final[frozenset[str]] = frozenset({
    "bool",
    "byte",
    "cap",
    "close",
    "complex",
    "complex64",
    "complex128",
    "copy",
    "delete",
    "error",
    "false",
    "float32",
    "float64",
    "imag",
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "iota",
    "len",
    "make",
    "new",
    "nil",
    "panic",
    "print",
    "println",
    "real",
    "recover",
    "rune",
    "string",
    "true",
    "uint",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "uintptr",
})

# Package names imported by the generated Go file template (go_file.go.j2).
# Update this set when template imports change.
_IMPORT_NAMES: Final[frozenset[str]] = frozenset({
    "purego",
    "unsafe",
    "fmt",
    "strings",
})

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
    """Check whether one token is a valid Go identifier.

    Returns:
        `True` when `value` is a valid Go identifier.
    """
    return GO_IDENTIFIER_PATTERN.fullmatch(value) is not None


def is_go_identifier_prefix(value: str) -> bool:
    """Check whether a value is a valid generated identifier prefix.

    Returns:
        `True` when `value` is a valid Go identifier ending with `_`.
    """
    return value.endswith("_") and is_go_identifier(value[:-1])


def sanitize_identifier(
    raw: str,
    *,
    fallback: str,
    digit_prefix: str,
    strip_outer_underscores: bool,
) -> str:
    """Normalize arbitrary text into one Go identifier token.

    Returns:
        Sanitized identifier token.
    """
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
    """Normalize struct-field names for parser struct literal emission.

    Returns:
        Sanitized struct field identifier.
    """
    return sanitize_identifier(
        raw,
        fallback=fallback,
        digit_prefix="f_",
        strip_outer_underscores=True,
    )


def sanitize_symbol_suffix(raw: str, *, fallback: str) -> str:
    """Normalize generated declaration suffix preserving source casing.

    Returns:
        Sanitized declaration suffix identifier.
    """
    return sanitize_identifier(
        raw,
        fallback=fallback,
        digit_prefix="n_",
        strip_outer_underscores=False,
    )


def allocate_unique_identifier(base_identifier: str, *, seen: set[str]) -> str:
    """Allocate a deterministic unique identifier in one category.

    Returns:
        Unique identifier that is recorded in `seen`.
    """
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
    """Build deterministic unique identifiers for one declaration category.

    Returns:
        Identifier tuple in the same order as `raw_names`.
    """
    seen: set[str] = set()
    resolved: list[str] = []
    for index, raw_name in enumerate(raw_names, start=1):
        base_identifier = sanitize_symbol_suffix(raw_name, fallback=f"{fallback_prefix}_{index}")
        resolved.append(allocate_unique_identifier(base_identifier, seen=seen))
    return tuple(resolved)


def normalize_lib_id(value: str) -> str:
    """Normalize library id text to snake_case-safe identifier.

    Returns:
        Normalized library identifier.

    Raises:
        ValueError: Input contains no alphanumeric character.
    """
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    if not normalized:
        message = "--lib-id must contain at least one alphanumeric character."
        raise ValueError(message)
    if normalized[0].isdigit():
        normalized = f"lib_{normalized}"
    return normalized


def normalize_identifier_prefix(value: str, *, allow_empty: bool = False) -> str:
    """Validate and normalize the generated identifier prefix.

    Returns:
        Validated identifier prefix.

    Raises:
        ValueError: Input is not a valid Go identifier prefix ending with `_`.
    """
    if allow_empty and not value:
        return value
    if not is_go_identifier_prefix(value):
        message = (
            "identifier_prefix must match ^[A-Za-z_][A-Za-z0-9_]*_$ and end with an underscore."
        )
        raise ValueError(message)
    return value


def validate_generated_names(
    names: list[tuple[str, str, bool]],
) -> list[str]:
    """Validate generated names for collisions and Go naming issues.

    Args:
        names: List of ``(generated_go_name, origin_description,
            check_reserved)`` triples.  *check_reserved* is ``True``
            for names from categories whose prefix is empty; only those
            are checked against Go keywords, predeclared identifiers,
            and import names.  Cross-category collision detection always
            applies to every entry.

    Returns:
        List of error messages.  Empty when all names are valid.
    """
    errors: list[str] = []
    seen: dict[str, str] = {}

    for name, origin, check_reserved in names:
        # Cross-category collision — always checked.
        if name in seen:
            errors.append(
                f"generated name {name!r} ({origin}) collides with "
                f"previously generated name ({seen[name]}); "
                "set identifier_prefix or a per-category prefix in config"
            )
        else:
            seen[name] = origin

        if not check_reserved:
            continue

        if name in GO_KEYWORDS:
            errors.append(
                f"generated name {name!r} ({origin}) collides with Go keyword; "
                "set identifier_prefix or a per-category prefix in config"
            )
        if name in GO_PREDECLARED:
            errors.append(
                f"generated name {name!r} ({origin}) shadows Go predeclared identifier; "
                "set identifier_prefix or a per-category prefix in config"
            )
        if name in _IMPORT_NAMES:
            errors.append(
                f"generated name {name!r} ({origin}) shadows import name; "
                "set identifier_prefix or a per-category prefix in config"
            )

    return errors


def accessor_getter_name(c_field_name: str) -> str:
    """Build an exported getter method name preserving the original C field name.

    Returns:
        Getter name in ``Get_<c_name>`` form.
    """
    return f"Get_{c_field_name}"


def accessor_setter_name(c_field_name: str) -> str:
    """Build an exported setter method name preserving the original C field name.

    Returns:
        Setter name in ``Set_<c_name>`` form.
    """
    return f"Set_{c_field_name}"


__all__ = [
    "GO_IDENTIFIER_PATTERN",
    "GO_KEYWORDS",
    "GO_PREDECLARED",
    "accessor_getter_name",
    "accessor_setter_name",
    "allocate_unique_identifier",
    "build_unique_identifiers",
    "is_go_identifier",
    "is_go_identifier_prefix",
    "normalize_identifier_prefix",
    "normalize_lib_id",
    "sanitize_identifier",
    "sanitize_struct_field_identifier",
    "sanitize_symbol_suffix",
    "validate_generated_names",
]
