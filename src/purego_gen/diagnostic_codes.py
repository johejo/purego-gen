# Copyright (c) 2026 purego-gen contributors.

"""Stable diagnostic code helpers."""

from __future__ import annotations

from typing import Final

DIAGNOSTIC_CODE_PREFIX: Final[str] = "PUREGO_GEN"


def build_diagnostic_code(*parts: str) -> str:
    """Build one stable diagnostic code from upper-case segments.

    Returns:
        A diagnostic code prefixed with ``PUREGO_GEN``.
    """
    return "_".join((DIAGNOSTIC_CODE_PREFIX, *parts))
