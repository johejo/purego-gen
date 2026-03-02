# Copyright (c) 2026 purego-gen contributors.

"""Objective harness tests for libzstd (M5 baseline target)."""

from __future__ import annotations

import os
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from purego_gen.cli_invocation import (
    PuregoGenInvocation,
    build_purego_gen_command,
    build_src_pythonpath_env,
)
from purego_gen.pkg_config import run_pkg_config_stdout, run_pkg_config_tokens
from purego_gen.target_profile import TargetProfile, load_target_profile_catalog

from .helper.go_test_harness import run_go_test_in_generated_module

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"
_GO_COMPILE_FIXTURE_DIR = _FIXTURES_DIR / "go_compile_module"
_GO_RUNTIME_FIXTURE_DIR = _FIXTURES_DIR / "go_runtime_zstd_module"
_LIBZSTD_PROFILE_GOLDEN_PATH = _GOLDEN_DIR / "libzstd_profile" / "generated.go"
_LIBZSTD_STRICT_PROFILE_GOLDEN_PATH = _GOLDEN_DIR / "libzstd_strict_profile" / "generated.go"
_TARGET_PROFILES_DIR = _FIXTURES_DIR / "target_profiles"
_TARGET_PROFILE_CATALOG_PATH = _TARGET_PROFILES_DIR / "libzstd_profiles.json"
_LIBZSTD_PROFILE_ID = "libzstd_v1"
_LIBZSTD_STRICT_PROFILE_ID = "libzstd_strict"
_LIBRARY_OVERRIDE_ENV = "PUREGO_GEN_TEST_LIBZSTD"
_GOLDEN_OUTPUT_PACKAGE = "fixture"
_STRICT_GOLDEN_OUTPUT_PACKAGE = "zstdfixturestrict"
_RUNTIME_PACKAGE = "zstdfixture"
_LIBZSTD_MACRO_FILTER = (
    "^("
    "ZSTD_VERSION_MAJOR|"
    "ZSTD_VERSION_MINOR|"
    "ZSTD_VERSION_RELEASE|"
    "ZSTD_MAGICNUMBER|"
    "ZSTD_CONTENTSIZE_UNKNOWN|"
    "ZSTD_CONTENTSIZE_ERROR"
    ")$"
)


@dataclass(frozen=True, slots=True)
class _LibzstdHarnessConfig:
    """Resolved harness inputs for libzstd target tests."""

    include_dir: Path
    clang_args: tuple[str, ...]
    shared_library_path: Path


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
    clang_args = run_pkg_config_tokens("libzstd", "--cflags")
    include_dir = Path(run_pkg_config_stdout("libzstd", "--variable=includedir")).expanduser()
    if not include_dir.is_dir():
        message = f"failed to resolve libzstd include directory from pkg-config: {include_dir}"
        raise RuntimeError(message)

    shared_library_override = os.environ.get(_LIBRARY_OVERRIDE_ENV, "").strip()
    if shared_library_override:
        shared_library_path = Path(shared_library_override).expanduser().resolve()
        if not shared_library_path.is_file():
            message = f"{_LIBRARY_OVERRIDE_ENV} does not point to a file: {shared_library_path}"
            raise RuntimeError(message)
        return _LibzstdHarnessConfig(
            include_dir=include_dir,
            clang_args=clang_args,
            shared_library_path=shared_library_path,
        )

    lib_dir = Path(run_pkg_config_stdout("libzstd", "--variable=libdir")).expanduser().resolve()
    shared_library_path = _resolve_shared_library_path(lib_dir)
    if shared_library_path is None:
        message = (
            "failed to resolve libzstd shared library path from pkg-config libdir. "
            f"Set {_LIBRARY_OVERRIDE_ENV} to an absolute shared-library path."
        )
        raise RuntimeError(message)

    return _LibzstdHarnessConfig(
        include_dir=include_dir,
        clang_args=clang_args,
        shared_library_path=shared_library_path,
    )


def _resolve_profile_headers(
    config: _LibzstdHarnessConfig,
    *,
    profile: TargetProfile,
) -> tuple[Path, ...]:
    """Resolve profile-defined header names from pkg-config include directory.

    Returns:
        Header path tuple in profile-defined order.

    Raises:
        RuntimeError: One or more headers cannot be resolved.
    """
    resolved: list[Path] = []
    for header_name in profile.header_names:
        header_path = (config.include_dir / header_name).resolve()
        if not header_path.is_file():
            message = f"failed to locate {header_name} from pkg-config includedir: {header_path}"
            raise RuntimeError(message)
        resolved.append(header_path)
    return tuple(resolved)


def _run_cli_for_libzstd(
    config: _LibzstdHarnessConfig,
    *,
    profile: TargetProfile,
    package: str,
) -> subprocess.CompletedProcess[str]:
    """Run purego-gen against discovered libzstd header with deterministic filter.

    Returns:
        Completed process result for the CLI invocation.
    """
    command = build_purego_gen_command(
        PuregoGenInvocation(
            lib_id="zstd",
            header_paths=_resolve_profile_headers(config, profile=profile),
            package_name=package,
            emit_kinds=profile.emit_kinds,
            clang_args=config.clang_args,
            func_filter=profile.function_filter,
            type_filter=profile.type_filter,
            const_filter=profile.const_filter,
            type_mapping=profile.type_mapping,
        ),
        python_executable=sys.executable,
    )
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=build_src_pythonpath_env(src_dir=_SRC_DIR),
        text=True,
    )


def _run_cli_for_libzstd_constants(
    config: _LibzstdHarnessConfig,
    *,
    package: str,
    const_filter: str,
) -> subprocess.CompletedProcess[str]:
    """Run purego-gen against discovered libzstd header for constant extraction.

    Returns:
        Completed process result for the CLI invocation.

    Raises:
        RuntimeError: `zstd.h` cannot be resolved from pkg-config include dir.
    """
    header_path = (config.include_dir / "zstd.h").resolve()
    if not header_path.is_file():
        message = f"failed to locate zstd.h from pkg-config includedir: {header_path}"
        raise RuntimeError(message)
    command = build_purego_gen_command(
        PuregoGenInvocation(
            lib_id="zstd",
            header_paths=(header_path,),
            package_name=package,
            emit_kinds="const",
            clang_args=config.clang_args,
            const_filter=const_filter,
        ),
        python_executable=sys.executable,
    )
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=build_src_pythonpath_env(src_dir=_SRC_DIR),
        text=True,
    )


def _assert_go_source_compiles(source: str, tmp_path: Path) -> None:
    """Compile generated source in the shared Go fixture module."""
    result = run_go_test_in_generated_module(
        fixture_module_dir=_GO_COMPILE_FIXTURE_DIR,
        tmp_path=tmp_path,
        generated_source=source,
        output_dir_name="generated",
    )
    assert result.returncode == 0, result.stderr


def _assert_runtime_harness_passes(
    source: str,
    tmp_path: Path,
    *,
    shared_library_path: Path,
) -> None:
    """Run generated bindings in runtime harness against libzstd shared object."""
    result = run_go_test_in_generated_module(
        fixture_module_dir=_GO_RUNTIME_FIXTURE_DIR,
        tmp_path=tmp_path,
        generated_source=source,
        output_dir_name="runtime_generated",
        env_overrides={
            "CGO_ENABLED": "0",
            "PUREGO_GEN_TEST_LIB": str(shared_library_path),
        },
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="session")
def libzstd_harness_config() -> _LibzstdHarnessConfig:
    """Resolve libzstd harness configuration.

    Returns:
        Resolved harness configuration used by libzstd tests.
    """
    return _resolve_libzstd_harness_config()


@pytest.fixture(scope="session")
def libzstd_profile() -> TargetProfile:
    """Load stable libzstd profile for harness tests.

    Returns:
        Parsed profile used to build generation filters.
    """
    return load_target_profile_catalog(_TARGET_PROFILE_CATALOG_PATH, _LIBZSTD_PROFILE_ID)


@pytest.fixture(scope="session")
def libzstd_strict_profile() -> TargetProfile:
    """Load strict libzstd profile for strict typing harness tests.

    Returns:
        Parsed strict profile used to build generation filters.
    """
    return load_target_profile_catalog(_TARGET_PROFILE_CATALOG_PATH, _LIBZSTD_STRICT_PROFILE_ID)


def test_generates_libzstd_golden_output(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
    libzstd_profile: TargetProfile,
) -> None:
    """CLI output for libzstd profile should match committed golden output."""
    result = _run_cli_for_libzstd(
        libzstd_harness_config,
        profile=libzstd_profile,
        package=_GOLDEN_OUTPUT_PACKAGE,
    )
    expected = _LIBZSTD_PROFILE_GOLDEN_PATH.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    _assert_go_source_compiles(result.stdout, tmp_path)


def test_runtime_harness_resolves_libzstd_symbols(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
    libzstd_profile: TargetProfile,
) -> None:
    """Generated bindings should run a libzstd roundtrip in runtime harness."""
    result = _run_cli_for_libzstd(
        libzstd_harness_config,
        profile=libzstd_profile,
        package=_RUNTIME_PACKAGE,
    )
    assert result.returncode == 0, result.stderr
    _assert_runtime_harness_passes(
        result.stdout,
        tmp_path,
        shared_library_path=libzstd_harness_config.shared_library_path,
    )


def test_generates_libzstd_strict_golden_output(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
    libzstd_strict_profile: TargetProfile,
) -> None:
    """Strict profile output should match committed strict golden output."""
    result = _run_cli_for_libzstd(
        libzstd_harness_config,
        profile=libzstd_strict_profile,
        package=_STRICT_GOLDEN_OUTPUT_PACKAGE,
    )
    expected = _LIBZSTD_STRICT_PROFILE_GOLDEN_PATH.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    assert "purego_type_ZSTD_ErrorCode int32" in result.stdout
    assert ") purego_type_ZSTD_ErrorCode" in result.stdout
    assert "purego_const_ZSTD_CONTENTSIZE_UNKNOWN uint64" in result.stdout
    assert "purego_const_ZSTD_CONTENTSIZE_ERROR" in result.stdout
    assert "uint64 = 18446744073709551614" in result.stdout
    _assert_go_source_compiles(result.stdout, tmp_path)


def test_extracts_libzstd_object_like_macro_constants(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
) -> None:
    """CLI should extract required object-like macro constants for libzstd."""
    result = _run_cli_for_libzstd_constants(
        libzstd_harness_config,
        package=_GOLDEN_OUTPUT_PACKAGE,
        const_filter=_LIBZSTD_MACRO_FILTER,
    )
    assert result.returncode == 0, result.stderr
    assert "purego_const_ZSTD_VERSION_MAJOR" in result.stdout
    assert "purego_const_ZSTD_VERSION_MINOR" in result.stdout
    assert "purego_const_ZSTD_VERSION_RELEASE" in result.stdout
    assert "purego_const_ZSTD_MAGICNUMBER" in result.stdout
    assert "purego_const_ZSTD_CONTENTSIZE_UNKNOWN" in result.stdout
    assert "purego_const_ZSTD_CONTENTSIZE_ERROR" in result.stdout
    _assert_go_source_compiles(result.stdout, tmp_path)
