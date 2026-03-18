# Copyright (c) 2026 purego-gen contributors.

"""C type spelling helpers shared by CLI and renderer."""

from __future__ import annotations

import re
from typing import Final

_OPAQUE_POINTER_TYPEDEF_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:const|volatile|restrict)\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*\*(?:\s*(?:const|volatile|restrict))*$"
)
_FUNCTION_POINTER_C_TYPE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\(\s*\*\s*\)")
_ENUM_TYPEDEF_C_TYPE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^enum\s+([A-Za-z_][A-Za-z0-9_]*)$"
)
_C_TYPE_QUALIFIERS: Final[frozenset[str]] = frozenset({"const", "volatile", "restrict"})
_FUNCTION_POINTER_SIGNATURE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<result>.+?)\(\s*\*\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)?\s*\)\s*\((?P<params>.*)\)$"
)


def extract_pointer_typedef_name(c_type: str) -> str | None:
    """Extract typedef name from one single-pointer C type spelling.

    Returns:
        Matched typedef name when pattern matches, otherwise `None`.
    """
    normalized = " ".join(c_type.split())
    matched = _OPAQUE_POINTER_TYPEDEF_PATTERN.fullmatch(normalized)
    if matched is None:
        return None
    return matched.group(1)


def normalize_c_type_for_lookup(c_type: str) -> str:
    """Normalize C type spelling for deterministic lookup keys.

    Returns:
        Normalized C type string without qualifiers used in lookup keys.
    """
    tokens = [token for token in c_type.split() if token not in _C_TYPE_QUALIFIERS]
    return " ".join(tokens)


def is_function_pointer_c_type(c_type: str) -> bool:
    """Check whether one C type spelling represents a function pointer.

    Returns:
        `True` when the type spelling contains a function-pointer declarator.
    """
    return _FUNCTION_POINTER_C_TYPE_PATTERN.search(normalize_c_type_for_lookup(c_type)) is not None


def normalize_function_pointer_c_type_for_lookup(c_type: str) -> str:
    """Normalize function-pointer type spelling for deterministic lookup keys.

    Returns:
        Whitespace-free lookup key for function-pointer type spellings.
    """
    return re.sub(r"\s+", "", normalize_c_type_for_lookup(c_type))


def extract_enum_typedef_name(c_type: str) -> str | None:
    """Extract enum target name from typedef C type spelling.

    Returns:
        Enum target name when pattern matches, otherwise `None`.
    """
    normalized = normalize_c_type_for_lookup(c_type)
    matched = _ENUM_TYPEDEF_C_TYPE_PATTERN.fullmatch(normalized)
    if matched is None:
        return None
    return matched.group(1)


def split_c_parameter_list(parameter_list: str) -> tuple[str, ...]:
    """Split one C parameter list while respecting nested parentheses.

    Returns:
        Tuple of raw parameter type spellings.

    Raises:
        ValueError: Parentheses are unbalanced.
    """
    normalized = parameter_list.strip()
    if not normalized:
        return ()
    if normalized == "void":
        return ()

    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in normalized:
        depth, flushed_part = _consume_c_parameter_list_char(
            char=char,
            depth=depth,
            current=current,
            parameter_list=parameter_list,
        )
        if flushed_part is not None:
            parts.append(flushed_part)

    if depth != 0:
        message = f"unbalanced C parameter list: {parameter_list}"
        raise ValueError(message)

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


def _consume_c_parameter_list_char(
    *,
    char: str,
    depth: int,
    current: list[str],
    parameter_list: str,
) -> tuple[int, str | None]:
    """Consume one character while splitting a C parameter list.

    Returns:
        Updated parenthesis depth and an optional flushed parameter part.

    Raises:
        ValueError: Parentheses are unbalanced.
    """
    if char == "," and depth == 0:
        part = "".join(current).strip()
        current.clear()
        return depth, part or None
    if char == "(":
        depth += 1
    elif char == ")":
        depth -= 1
        if depth < 0:
            message = f"unbalanced C parameter list: {parameter_list}"
            raise ValueError(message)
    current.append(char)
    return depth, None


def parse_function_pointer_c_type(
    c_type: str,
) -> tuple[str, str | None, tuple[str, ...]] | None:
    """Parse one function-pointer C type spelling.

    Returns:
        Tuple of result type, optional declarator name, and parameter types, or
        `None` when the spelling is not a function pointer.
    """
    normalized = " ".join(c_type.split())
    matched = _FUNCTION_POINTER_SIGNATURE_PATTERN.fullmatch(normalized)
    if matched is None:
        return None
    return (
        matched.group("result").strip(),
        matched.group("name"),
        split_c_parameter_list(matched.group("params")),
    )
