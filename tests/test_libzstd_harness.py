# Copyright (c) 2026 purego-gen contributors.

"""Objective harness tests for libzstd (M5 baseline target)."""

from __future__ import annotations

import json
import os
import re
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from purego_gen.go_test_harness import run_go_test_in_generated_module
from purego_gen.model import TypeMappingOptions
from purego_gen.pkg_config import run_pkg_config_stdout, run_pkg_config_tokens

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"
_GO_COMPILE_FIXTURE_DIR = _FIXTURES_DIR / "go_compile_module"
_GO_RUNTIME_FIXTURE_DIR = _FIXTURES_DIR / "go_runtime_zstd_module"
_LIBZSTD_PROFILE_GOLDEN_PATH = _GOLDEN_DIR / "libzstd_profile" / "generated.go"
_TARGET_PROFILES_DIR = _FIXTURES_DIR / "target_profiles"
_LIBZSTD_PROFILE_PATH = _TARGET_PROFILES_DIR / "libzstd_v1.json"
_LIBRARY_OVERRIDE_ENV = "PUREGO_GEN_TEST_LIBZSTD"
_HEADER_NAME = "zstd.h"
_GOLDEN_OUTPUT_PACKAGE = "fixture"
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
class _LibzstdProfile:
    """Stable profile used by libzstd objective harness."""

    profile_id: str
    emit_kinds: str
    required_functions: tuple[str, ...]
    required_types: tuple[str, ...]
    function_filter: str
    type_filter: str
    type_mapping: TypeMappingOptions


@dataclass(frozen=True, slots=True)
class _LibzstdHarnessConfig:
    """Resolved harness inputs for libzstd target tests."""

    header_path: Path
    clang_args: tuple[str, ...]
    shared_library_path: Path


def _build_exact_symbol_regex(symbols: tuple[str, ...]) -> str:
    """Build exact-match regex from symbol names.

    Returns:
        Regex pattern that matches symbols exactly.
    """
    escaped = [re.escape(symbol) for symbol in symbols]
    return "^(" + "|".join(escaped) + ")$"


def _read_required_non_empty_string(raw: dict[str, object], key: str) -> str:
    """Read one required non-empty string field from profile JSON object.

    Returns:
        String value for `key`.

    Raises:
        RuntimeError: The field is missing or empty.
    """
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        message = f"libzstd profile must define non-empty string `{key}`."
        raise RuntimeError(message)
    return value


def _read_required_non_empty_string_array(raw: dict[str, object], key: str) -> tuple[str, ...]:
    """Read one required non-empty string array field from profile JSON object.

    Returns:
        Tuple of string values for `key`.

    Raises:
        RuntimeError: The field is missing, empty, or includes non-string/empty items.
    """
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        message = f"libzstd profile must define non-empty array `{key}`."
        raise RuntimeError(message)
    items: list[str] = []
    for element in cast("list[object]", value):
        if not isinstance(element, str) or not element:
            message = f"libzstd profile `{key}` must contain non-empty strings."
            raise RuntimeError(message)
        items.append(element)
    return tuple(items)


def _read_required_bool(raw: dict[str, object], key: str) -> bool:
    """Read one required bool field from profile JSON object.

    Returns:
        Bool value for `key`.

    Raises:
        TypeError: The field is missing or not a bool.
    """
    value = raw.get(key)
    if not isinstance(value, bool):
        message = f"libzstd profile must define bool `{key}`."
        raise TypeError(message)
    return value


def _read_type_mapping_options(raw: dict[str, object]) -> TypeMappingOptions:
    """Read type-mapping options from profile JSON object.

    Returns:
        Parsed type-mapping option set.

    Raises:
        TypeError: Type-mapping profile section is malformed.
    """
    raw_type_mapping = raw.get("type_mapping")
    if not isinstance(raw_type_mapping, dict):
        message = "libzstd profile `type_mapping` must be a JSON object."
        raise TypeError(message)
    type_mapping_dict = cast("dict[str, object]", raw_type_mapping)
    return TypeMappingOptions(
        const_char_as_string=_read_required_bool(type_mapping_dict, "const_char_as_string")
    )


def _load_libzstd_profile() -> _LibzstdProfile:
    """Load stable v1 profile used by libzstd harness tests.

    Returns:
        Parsed profile model.

    Raises:
        RuntimeError: Profile file is missing or malformed.
        TypeError: Profile JSON root is not an object.
    """
    if not _LIBZSTD_PROFILE_PATH.is_file():
        message = f"libzstd profile not found: {_LIBZSTD_PROFILE_PATH}"
        raise RuntimeError(message)

    try:
        raw_object = cast("object", json.loads(_LIBZSTD_PROFILE_PATH.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        message = f"failed to parse libzstd profile JSON: {error}"
        raise RuntimeError(message) from error
    if not isinstance(raw_object, dict):
        message = "libzstd profile root must be a JSON object."
        raise TypeError(message)
    raw = cast("dict[str, object]", raw_object)

    profile_id = _read_required_non_empty_string(raw, "profile_id")
    emit_kinds = _read_required_non_empty_string(raw, "emit_kinds")
    required_functions = _read_required_non_empty_string_array(raw, "required_functions")
    required_types = _read_required_non_empty_string_array(raw, "required_types")
    type_mapping = _read_type_mapping_options(raw)
    return _LibzstdProfile(
        profile_id=profile_id,
        emit_kinds=emit_kinds,
        required_functions=required_functions,
        required_types=required_types,
        function_filter=_build_exact_symbol_regex(required_functions),
        type_filter=_build_exact_symbol_regex(required_types),
        type_mapping=type_mapping,
    )


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

    lib_dir = Path(run_pkg_config_stdout("libzstd", "--variable=libdir")).expanduser().resolve()
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


def _run_cli_for_libzstd(
    config: _LibzstdHarnessConfig,
    *,
    profile: _LibzstdProfile,
    package: str,
) -> subprocess.CompletedProcess[str]:
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
        package,
        "--emit",
        profile.emit_kinds,
        "--func-filter",
        profile.function_filter,
        "--type-filter",
        profile.type_filter,
    ]
    if profile.type_mapping.const_char_as_string:
        command.append("--const-char-as-string")
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


def _run_cli_for_libzstd_constants(
    config: _LibzstdHarnessConfig,
    *,
    package: str,
    const_filter: str,
) -> subprocess.CompletedProcess[str]:
    """Run purego-gen against discovered libzstd header for constant extraction.

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
        package,
        "--emit",
        "const",
        "--const-filter",
        const_filter,
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
def libzstd_profile() -> _LibzstdProfile:
    """Load stable libzstd profile for harness tests.

    Returns:
        Parsed profile used to build generation filters.
    """
    return _load_libzstd_profile()


def test_generates_libzstd_golden_output(
    tmp_path: Path,
    libzstd_harness_config: _LibzstdHarnessConfig,
    libzstd_profile: _LibzstdProfile,
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
    libzstd_profile: _LibzstdProfile,
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
