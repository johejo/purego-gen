# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201

"""C type spelling helpers shared by CLI and renderer."""

from __future__ import annotations

import re
from typing import Final

_OPAQUE_POINTER_TYPEDEF_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:const|volatile|restrict)\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*\*(?:\s*(?:const|volatile|restrict))*$"
)
_ENUM_TYPEDEF_C_TYPE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^enum\s+([A-Za-z_][A-Za-z0-9_]*)$"
)
_C_TYPE_QUALIFIERS: Final[frozenset[str]] = frozenset({"const", "volatile", "restrict"})


def extract_pointer_typedef_name(c_type: str) -> str | None:
    """Extract typedef name from one single-pointer C type spelling."""
    normalized = " ".join(c_type.split())
    matched = _OPAQUE_POINTER_TYPEDEF_PATTERN.fullmatch(normalized)
    if matched is None:
        return None
    return matched.group(1)


def normalize_c_type_for_lookup(c_type: str) -> str:
    """Normalize C type spelling for deterministic lookup keys."""
    tokens = [token for token in c_type.split() if token not in _C_TYPE_QUALIFIERS]
    return " ".join(tokens)


def extract_enum_typedef_name(c_type: str) -> str | None:
    """Extract enum target name from typedef C type spelling."""
    normalized = normalize_c_type_for_lookup(c_type)
    matched = _ENUM_TYPEDEF_C_TYPE_PATTERN.fullmatch(normalized)
    if matched is None:
        return None
    return matched.group(1)
