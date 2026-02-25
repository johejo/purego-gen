# Copyright (c) 2026 purego-gen contributors.

"""Helpers for running Go test harness modules from Python tests."""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404
from typing import TYPE_CHECKING

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
) -> subprocess.CompletedProcess[str]:
    """Run `go test ./...` after writing generated source into a fixture module.

    Args:
        fixture_module_dir: Go module fixture directory to copy into temp space.
        tmp_path: Temporary test root path.
        generated_source: Go source text to write into `generated.go`.
        output_dir_name: Subdirectory name created under `tmp_path`.
        env_overrides: Optional environment key-value overrides.

    Returns:
        Completed process result from `go test`.

    Raises:
        RuntimeError: `go` binary is unavailable in `PATH`.
    """
    go_binary = shutil.which("go")
    if go_binary is None:
        message = "go is not available in PATH."
        raise RuntimeError(message)

    module_dir = tmp_path / output_dir_name
    shutil.copytree(fixture_module_dir, module_dir)
    (module_dir / "generated.go").write_text(generated_source, encoding="utf-8")

    env = os.environ.copy()
    if env_overrides is not None:
        env.update(env_overrides)

    return subprocess.run(  # noqa: S603
        [go_binary, "test", "./..."],
        capture_output=True,
        check=False,
        cwd=module_dir,
        env=env,
        text=True,
    )
