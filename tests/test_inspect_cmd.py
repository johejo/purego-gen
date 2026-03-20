# Copyright (c) 2026 purego-gen contributors.

"""Tests for ``purego-gen inspect`` subcommand."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from purego_gen.process_exec import CommandResult, run_command

from .helper.stdout_assertions import assert_text_contains_fragments

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"


def _run_inspect(*args: str) -> CommandResult:
    """Run ``purego-gen inspect`` via subprocess for end-to-end behavior checks.

    Returns:
        Completed process result.
    """
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(_SRC_DIR)
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}:{existing_pythonpath}"
    )
    return run_command(
        [sys.executable, "-m", "purego_gen", "inspect", *args],
        cwd=_REPO_ROOT,
        env=env,
    )


def test_inspect_exits_zero_for_local_fixture_header() -> None:
    """Inspect subcommand should complete successfully for local fixture header."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "basic.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--sample-size",
        "0",
    )
    assert result.returncode == 0, result.stderr
    assert_text_contains_fragments(
        result.stdout,
        (
            "package=manual",
            "opaque_record_typedefs=",
            "sample_opaque_record_typedefs:",
        ),
    )
