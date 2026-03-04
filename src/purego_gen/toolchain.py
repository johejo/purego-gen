# Copyright (c) 2026 purego-gen contributors.

"""Toolchain resolution helpers."""

from __future__ import annotations

import os
import shlex
import shutil


def resolve_c_compiler_command(*, purpose: str) -> list[str]:
    """Resolve C compiler command from environment with clang fallback.

    Args:
        purpose: Human-readable context for error messages.

    Returns:
        Compiler command tokens.

    Raises:
        RuntimeError: Compiler command cannot be resolved.
    """
    cc_value = os.environ.get("CC", "").strip()
    if cc_value:
        command = shlex.split(cc_value)
        if not command:
            message = "CC is empty after parsing."
            raise RuntimeError(message)
        return command

    clang_binary = shutil.which("clang")
    if clang_binary is not None:
        return [clang_binary]
    message = f"clang is required for {purpose}"
    raise RuntimeError(message)
