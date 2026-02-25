# Copyright (c) 2026 purego-gen contributors.

"""Smoke tests for `scripts/inspect-target-library.py`."""

from __future__ import annotations

import os
import subprocess  # noqa: S404
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "inspect-target-library.py"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
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
    return subprocess.run(  # noqa: S603
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
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
