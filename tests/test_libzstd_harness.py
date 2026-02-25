# Copyright (c) 2026 purego-gen contributors.

"""Objective harness tests for libzstd (M5 baseline target)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"
_GO_COMPILE_FIXTURE_DIR = _FIXTURES_DIR / "go_compile_module"
_GO_RUNTIME_FIXTURE_DIR = _FIXTURES_DIR / "go_runtime_zstd_module"
_LIBZSTD_GOLDEN_PATH = _GOLDEN_DIR / "libzstd_core.go"
_LIBZSTD_FUNCTION_FILTER = r"^ZSTD_(versionNumber|compressBound|isError)$"
_LIBRARY_OVERRIDE_ENV = "PUREGO_GEN_TEST_LIBZSTD"
_HEADER_NAME = "zstd.h"


@dataclass(frozen=True, slots=True)
class _LibzstdHarnessConfig:
    """Resolved harness inputs for libzstd target tests."""

    header_path: Path
    clang_args: tuple[str, ...]
    shared_library_path: Path


def _shell_split(value: str) -> tuple[str, ...]:
    """Split shell-style flag text into tokens.

    Returns:
        Tokenized flag text.
    """
    stripped = value.strip()
    if not stripped:
        return ()
    return tuple(shlex.split(stripped))


def _run_pkg_config_stdout(*args: str) -> str:
    """Run pkg-config and return stripped stdout for one query.

    Returns:
        Command stdout with trailing whitespace trimmed.

    Raises:
        RuntimeError: `pkg-config` is unavailable or query fails.
    """
    pkg_config_binary = shutil.which("pkg-config")
    if pkg_config_binary is None:
        message = "pkg-config is required for libzstd harness tests (run via nix develop)."
        raise RuntimeError(message)

    result = subprocess.run(  # noqa: S603
        [pkg_config_binary, *args],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "pkg-config query failed"
        query = " ".join(args)
        message = f"pkg-config {query} failed for libzstd: {detail}"
        raise RuntimeError(message)
    return result.stdout.strip()


def _resolve_shared_library_path(library_dir: Path) -> Path | None:
    """Resolve libzstd shared-library path from pkg-config library directory.

    Returns:
        Resolved shared-library path when found, otherwise `None`.
    """
    if sys.platform == "darwin":
        exact_names = ("libzstd.dylib",)
        glob_patterns: tuple[str, ...] = ()
    else:
        exact_names = ("libzstd.so",)
        glob_patterns = ("libzstd.so.*",)

    for name in exact_names:
        candidate = (library_dir / name).resolve()
        if candidate.is_file():
            return candidate
    for pattern in glob_patterns:
        matches = sorted(path.resolve() for path in library_dir.glob(pattern) if path.is_file())
        if matches:
            return matches[0]
    return None


def _resolve_libzstd_harness_config() -> _LibzstdHarnessConfig:
    """Resolve header path, clang args, and shared library path for libzstd.

    Returns:
        Resolved target-library harness configuration.

    Raises:
        RuntimeError: Header or shared-library discovery fails.
    """
    clang_args = _shell_split(_run_pkg_config_stdout("--cflags", "libzstd"))
    include_dir = Path(_run_pkg_config_stdout("--variable=includedir", "libzstd")).expanduser()
    header_path = (include_dir / _HEADER_NAME).resolve()
    if not header_path.is_file():
        message = f"failed to locate zstd.h from pkg-config includedir: {header_path}"
        raise RuntimeError(message)

    shared_library_override = os.environ.get(_LIBRARY_OVERRIDE_ENV, "").strip()
    if shared_library_override:
        shared_library_path = Path(shared_library_override).expanduser().resolve()
        if not shared_library_path.is_file():
            message = f"{_LIBRARY_OVERRIDE_ENV} does not point to a file: {shared_library_path}"
            raise RuntimeError(message)
        return _LibzstdHarnessConfig(
            header_path=header_path,
            clang_args=clang_args,
            shared_library_path=shared_library_path,
        )

    lib_dir = Path(_run_pkg_config_stdout("--variable=libdir", "libzstd")).expanduser().resolve()
    shared_library_path = _resolve_shared_library_path(lib_dir)
    if shared_library_path is None:
        message = (
            "failed to resolve libzstd shared library path from pkg-config libdir. "
            f"Set {_LIBRARY_OVERRIDE_ENV} to an absolute shared-library path."
        )
        raise RuntimeError(message)

    return _LibzstdHarnessConfig(
        header_path=header_path,
        clang_args=clang_args,
        shared_library_path=shared_library_path,
    )


def _run_cli_for_libzstd(config: _LibzstdHarnessConfig) -> subprocess.CompletedProcess[str]:
    """Run purego-gen against discovered libzstd header with deterministic filter.

    Returns:
        Completed process result for the CLI invocation.
    """
    command = [
        sys.executable,
        "-m",
        "purego_gen",
        "--lib-id",
        "zstd",
        "--header",
        str(config.header_path),
        "--pkg",
        "zstdfixture",
        "--emit",
        "func",
        "--func-filter",
        _LIBZSTD_FUNCTION_FILTER,
    ]
    if config.clang_args:
        command.extend(["--", *config.clang_args])

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(_SRC_DIR)
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}:{existing_pythonpath}"
    )
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )


def _assert_go_source_compiles(source: str, tmp_path: Path) -> None:
    """Compile generated source in the shared Go fixture module."""
    go_binary = shutil.which("go")
    assert go_binary is not None

    module_dir = tmp_path / "generated"
    shutil.copytree(_GO_COMPILE_FIXTURE_DIR, module_dir)
    (module_dir / "generated.go").write_text(source, encoding="utf-8")

    result = subprocess.run(  # noqa: S603
        [go_binary, "test", "./..."],
        capture_output=True,
        check=False,
        cwd=module_dir,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _assert_runtime_harness_passes(
    source: str,
    tmp_path: Path,
    *,
    shared_library_path: Path,
) -> None:
    """Run generated bindings in runtime harness against libzstd shared object."""
    go_binary = shutil.which("go")
    assert go_binary is not None

    module_dir = tmp_path / "runtime_generated"
    shutil.copytree(_GO_RUNTIME_FIXTURE_DIR, module_dir)
    (module_dir / "generated.go").write_text(source, encoding="utf-8")

    env = os.environ.copy()
    env["CGO_ENABLED"] = "0"
    env["PUREGO_GEN_TEST_LIB"] = str(shared_library_path)

    result = subprocess.run(  # noqa: S603
        [go_binary, "test", "./..."],
        capture_output=True,
        check=False,
        cwd=module_dir,
        env=env,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="session")
def libzstd_harness_config() -> _LibzstdHarnessConfig:
    """Skip session when libzstd harness prerequisites are unavailable.

    Returns:
        Resolved harness configuration used by libzstd tests.
    """
    try:
        return _resolve_libzstd_harness_config()
    except RuntimeError as error:
        pytest.skip(str(error))


def test_generates_libzstd_golden_output(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
) -> None:
    """CLI output for selected libzstd APIs should match committed golden output."""
    result = _run_cli_for_libzstd(libzstd_harness_config)
    expected = _LIBZSTD_GOLDEN_PATH.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    _assert_go_source_compiles(result.stdout, tmp_path)


def test_runtime_harness_resolves_libzstd_symbols(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
) -> None:
    """Generated register flow should resolve selected libzstd symbols at runtime."""
    result = _run_cli_for_libzstd(libzstd_harness_config)
    assert result.returncode == 0, result.stderr
    _assert_runtime_harness_passes(
        result.stdout,
        tmp_path,
        shared_library_path=libzstd_harness_config.shared_library_path,
    )
