# Copyright (c) 2026 purego-gen contributors.

"""Small helpers for querying pkg-config from tests and harness code."""

from __future__ import annotations

import shlex
import shutil
import subprocess  # noqa: S404


def run_pkg_config_stdout(package: str, *query_args: str) -> str:
    """Run one pkg-config query and return stdout.

    Args:
        package: pkg-config module name.
        query_args: Query options like `--cflags` or `--variable=libdir`.

    Returns:
        Query stdout with trailing whitespace trimmed.

    Raises:
        RuntimeError: `pkg-config` is unavailable or query fails.
    """
    pkg_config_binary = shutil.which("pkg-config")
    if pkg_config_binary is None:
        message = "pkg-config is required for harness tests (run via nix develop)."
        raise RuntimeError(message)

    command = [pkg_config_binary, *query_args, package]
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "pkg-config query failed"
        rendered_command = " ".join([*query_args, package])
        message = f"pkg-config {rendered_command} failed: {detail}"
        raise RuntimeError(message)
    return result.stdout.strip()


def run_pkg_config_tokens(package: str, *query_args: str) -> tuple[str, ...]:
    """Run one pkg-config query and split stdout as shell tokens.

    Args:
        package: pkg-config module name.
        query_args: Query options like `--cflags` or `--libs`.

    Returns:
        Tokenized query stdout.
    """
    return tuple(shlex.split(run_pkg_config_stdout(package, *query_args)))
