# Copyright (c) 2026 purego-gen contributors.

"""Helpers for running Go test harness modules from Python tests."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from purego_gen.process_exec import CommandResult, run_command

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def run_go_test_in_generated_module(
    *,
    fixture_module_dir: Path,
    tmp_path: Path,
    generated_source: str,
    output_dir_name: str,
    env_overrides: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run `go test ./...` after writing generated source into a fixture module.

    Args:
        fixture_module_dir: Go module fixture directory to copy into temp space.
        tmp_path: Temporary test root path.
        generated_source: Go source text to write into `generated.go`.
        output_dir_name: Subdirectory name created under `tmp_path`.
        env_overrides: Optional environment key-value overrides.

    Returns:
        Command result from `go test`.

    Raises:
        RuntimeError: `go` binary is unavailable in `PATH`.
    """
    go_binary = shutil.which("go")
    if go_binary is None:
        message = "go is not available in PATH."
        raise RuntimeError(message)

    module_dir = tmp_path / output_dir_name
    shutil.copytree(fixture_module_dir, module_dir)
    fixture_root_dir = fixture_module_dir.parent
    go_mod_path = fixture_root_dir / "go.mod"
    go_sum_path = fixture_root_dir / "go.sum"
    if not go_mod_path.is_file() or not go_sum_path.is_file():
        message = f"go.mod/go.sum not found under fixture root: {fixture_root_dir}"
        raise RuntimeError(message)
    (module_dir / "go.mod").write_text(go_mod_path.read_text(encoding="utf-8"))
    (module_dir / "go.sum").write_text(go_sum_path.read_text(encoding="utf-8"))
    (module_dir / "generated.go").write_text(generated_source, encoding="utf-8")

    env = os.environ.copy()
    if env_overrides is not None:
        env.update(env_overrides)

    return run_command(
        [go_binary, "test", "./..."],
        cwd=module_dir,
        env=env,
    )
