# Copyright (c) 2026 purego-gen contributors.

"""Utilities for rendering pydantic validation errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pydantic import ValidationError


def _render_location(location: tuple[object, ...]) -> str:
    rendered = ""
    for component in location:
        if isinstance(component, int):
            rendered += f"[{component}]"
            continue
        if rendered:
            rendered += "."
        rendered += str(component)
    return rendered or "<root>"


def _to_location(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return cast("tuple[object, ...]", value)
    if isinstance(value, list):
        return tuple(cast("list[object]", value))
    return ()


def format_validation_error(error: ValidationError, *, context: str) -> str:
    """Format `ValidationError` into stable path-prefixed lines.

    Returns:
        Human-readable multi-line validation failure description.
    """
    lines: list[str] = []
    raw_errors = cast("list[dict[str, object]]", error.errors(include_url=False))
    for details in raw_errors:
        location = _to_location(details.get("loc", ()))
        message = str(details.get("msg", "validation error"))
        error_type = str(details.get("type", "unknown"))
        lines.append(f"{_render_location(location)}: {message} ({error_type})")
    bullet_lines = "\n".join(f"- {line}" for line in lines)
    return f"{context} is invalid:\n{bullet_lines}"
