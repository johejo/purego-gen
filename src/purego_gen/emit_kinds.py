# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, DOC501

"""Shared emit-kind parsing and validation helpers."""

from __future__ import annotations

from typing import Final

ALLOWED_EMIT_KINDS: Final[frozenset[str]] = frozenset({"func", "type", "const", "var"})


def parse_emit_kinds(value: str, *, option_name: str) -> tuple[str, ...]:
    """Parse and validate comma-separated emit kinds."""
    parsed = tuple(part.strip() for part in value.split(",") if part.strip())
    if not parsed:
        message = f"{option_name} must contain at least one category."
        raise ValueError(message)

    invalid = [kind for kind in parsed if kind not in ALLOWED_EMIT_KINDS]
    if invalid:
        message = (
            f"Unsupported emit category: {', '.join(invalid)}. "
            "Supported values: func,type,const,var."
        )
        raise ValueError(message)
    return parsed


def validate_emit_kinds(emit_kinds: tuple[str, ...], *, context: str) -> None:
    """Validate emit kinds in one internal processing context."""
    invalid = [kind for kind in emit_kinds if kind not in ALLOWED_EMIT_KINDS]
    if invalid:
        message = (
            f"{context} received unsupported emit categories: {', '.join(invalid)}. "
            "Supported values: func,type,const,var."
        )
        raise ValueError(message)
