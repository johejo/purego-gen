# Copyright (c) 2026 purego-gen contributors.

"""Smoke tests for `scripts/inspect_target_library.py`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from purego_gen.process_exec import CommandResult, run_command

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "inspect_target_library.py"


def _run_script(*args: str) -> CommandResult:
    """Run inspect script via Python for end-to-end behavior checks.

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
        [sys.executable, str(_SCRIPT_PATH), *args],
        cwd=_REPO_ROOT,
        env=env,
    )


def test_inspect_script_exits_zero_for_libzstd() -> None:
    """Inspect script should complete successfully for `libzstd` target."""
    result = _run_script(
        "--pkg-config-package",
        "libzstd",
        "--header",
        "zstd.h",
        "--sample-size",
        "0",
    )
    assert result.returncode == 0, result.stderr
    assert "opaque_record_typedefs=" in result.stdout
    assert "sample_opaque_record_typedefs:" in result.stdout
