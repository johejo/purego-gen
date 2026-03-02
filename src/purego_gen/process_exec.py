# Copyright (c) 2026 purego-gen contributors.

"""Safe command execution helpers shared by CLI, scripts, and tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result payload from one process execution."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


async def _run_command_async(
    args: tuple[str, ...],
    *,
    cwd: Path | str | None,
    env: Mapping[str, str] | None,
    stdin_text: str | None,
) -> CommandResult:
    """Execute one command asynchronously and capture text streams.

    Args:
        args: Command and arguments as already tokenized values.
        cwd: Optional working directory.
        env: Optional process environment.
        stdin_text: Optional UTF-8 text written to stdin.

    Returns:
        Process result with captured stdout/stderr and return code.
    """
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if isinstance(cwd, Path) else cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdin_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
    stdout_bytes, stderr_bytes = await process.communicate(stdin_bytes)
    return CommandResult(
        args=args,
        returncode=int(process.returncode or 0),
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
) -> CommandResult:
    """Execute one command and capture UTF-8 text streams.

    Args:
        args: Command and arguments as a token sequence.
        cwd: Optional working directory.
        env: Optional process environment.
        stdin_text: Optional UTF-8 text written to stdin.

    Returns:
        Process result with captured stdout/stderr and return code.

    Raises:
        ValueError: `args` is empty.
    """
    if not args:
        message = "command must not be empty"
        raise ValueError(message)
    return asyncio.run(
        _run_command_async(
            tuple(args),
            cwd=cwd,
            env=env,
            stdin_text=stdin_text,
        )
    )


__all__ = ["CommandResult", "run_command"]
