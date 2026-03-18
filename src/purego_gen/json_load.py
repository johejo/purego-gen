# Copyright (c) 2026 purego-gen contributors.

"""Shared JSON file loading helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from purego_gen.validation_error_format import format_validation_error

if TYPE_CHECKING:
    from pathlib import Path


def read_json_text(path: Path, *, missing_label: str = "config") -> str:
    """Read one JSON file as UTF-8 text.

    Returns:
        File contents.

    Raises:
        RuntimeError: The file is missing or unreadable.
    """
    if not path.is_file():
        message = f"{missing_label} not found: {path}"
        raise RuntimeError(message)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"failed to read {missing_label} JSON at {path}: {error}"
        raise RuntimeError(message) from error


def load_json_model[ModelT: BaseModel](
    path: Path,
    *,
    model_type: type[ModelT],
    context: str,
    missing_label: str = "config",
) -> ModelT:
    """Load one JSON file into a validated pydantic model.

    Returns:
        Parsed and validated pydantic model instance.

    Raises:
        RuntimeError: The file cannot be read or schema validation fails.
    """
    resolved_path = path.expanduser().resolve()
    raw_text = read_json_text(resolved_path, missing_label=missing_label)
    try:
        return model_type.model_validate_json(raw_text)
    except ValidationError as error:
        message = format_validation_error(error, context=context)
        raise RuntimeError(message) from error


__all__ = ["load_json_model", "read_json_text"]
