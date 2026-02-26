# Copyright (c) 2026 purego-gen contributors.

"""Fixture layout checks for editor-friendly Go test modules."""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES_ROOT = _REPO_ROOT / "tests" / "fixtures"
_SRC_DIR = _REPO_ROOT / "src"
_PLACEHOLDER_SCRIPT = _REPO_ROOT / "scripts" / "update-go-fixture-placeholders.py"
_RUNTIME_FIXTURE_DIRS = (
    _FIXTURES_ROOT / "go_runtime_module",
    _FIXTURES_ROOT / "go_runtime_string_module",
    _FIXTURES_ROOT / "go_runtime_zstd_module",
)


def _run_fixture_compile_check(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run compile-only `go test` for fixture modules.

    Returns:
        Completed process result for assertions.

    Raises:
        RuntimeError: `go` binary is unavailable in `PATH`.
    """
    go_binary = shutil.which("go")
    if go_binary is None:
        message = "go is not available in PATH."
        raise RuntimeError(message)

    env = os.environ.copy()
    go_cache_dir = tmp_path / "go-build"
    go_cache_dir.mkdir(parents=True, exist_ok=True)
    env["GOCACHE"] = str(go_cache_dir)

    return subprocess.run(  # noqa: S603
        [go_binary, "test", "-run", "^$", "./..."],
        capture_output=True,
        check=False,
        cwd=_FIXTURES_ROOT,
        env=env,
        text=True,
    )


def _run_placeholder_sync_check() -> subprocess.CompletedProcess[str]:
    """Run placeholder-sync check script in check mode.

    Returns:
        Completed process result for assertions.
    """
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(_SRC_DIR)
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}:{existing_pythonpath}"
    )
    return subprocess.run(  # noqa: S603
        [sys.executable, str(_PLACEHOLDER_SCRIPT), "--check"],
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )


def test_runtime_go_fixtures_have_placeholder_generated_go() -> None:
    """Runtime Go fixture modules should keep `generated.go` placeholders committed."""
    for fixture_dir in _RUNTIME_FIXTURE_DIRS:
        generated_path = fixture_dir / "generated.go"
        assert generated_path.is_file(), f"missing required fixture placeholder: {generated_path}"


def test_runtime_go_fixtures_compile_for_editor_sanity(tmp_path: Path) -> None:
    """Fixture runtime modules should compile without generated temp output."""
    result = _run_fixture_compile_check(tmp_path)
    assert result.returncode == 0, result.stderr


def test_runtime_go_fixtures_generated_placeholders_are_in_sync() -> None:
    """Runtime fixture placeholders should match current CLI-generated output."""
    result = _run_placeholder_sync_check()
    assert result.returncode == 0, result.stdout + result.stderr
