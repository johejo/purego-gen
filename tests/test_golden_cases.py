# Copyright (c) 2026 purego-gen contributors.

"""Tests for case-driven golden config loading and validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from purego_gen_e2e.golden_cases_config import load_case_config
from purego_gen_e2e.golden_cases_lib import (
    CompileCRuntime,
    EnvIncludeHeaders,
    EnvLibdirRuntime,
    LocalHeaders,
    discover_cases,
    resolve_env_libdir_runtime_library,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def _write_json(path: Path, raw: object) -> None:
    """Write one JSON file with deterministic formatting."""
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def _write_text_line(path: Path, line: str) -> None:
    """Write one-line text file with a trailing newline."""
    path.write_text(f"{line}\n", encoding="utf-8")


def _make_repo_layout(tmp_path: Path) -> Path:
    """Create minimal repository layout expected by discover_cases.

    Returns:
        Temporary repository root path.
    """
    repo_root = tmp_path
    (repo_root / "tests" / "cases").mkdir(parents=True, exist_ok=True)
    return repo_root


def _make_case(repo_root: Path, case_id: str, profile: object) -> Path:
    """Create one case directory with config and placeholder generated.go.

    Returns:
        Created case directory path.
    """
    case_dir = repo_root / "tests" / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_json(case_dir / "config.json", profile)
    _write_text_line(case_dir / "generated.go", "package fixture")
    return case_dir


def test_discover_cases_loads_local_profile(tmp_path: Path) -> None:
    """A minimal local-header case should parse successfully."""
    repo_root = _make_repo_layout(tmp_path)
    case_dir = _make_case(
        repo_root,
        "one",
        {
            "schema_version": 2,
            "generator": {
                "lib_id": "fixture_lib",
                "package": "fixture",
                "emit": ["func"],
                "parse": {
                    "headers": {
                        "kind": "local",
                        "headers": ["headers/basic.h"],
                    }
                },
            },
        },
    )
    (case_dir / "headers").mkdir(parents=True, exist_ok=True)
    _write_text_line(case_dir / "headers" / "basic.h", "int add(int a, int b);")

    cases = discover_cases(repo_root=repo_root, selected_case_ids=())

    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "one"
    assert isinstance(case.config.generator.parse.headers, LocalHeaders)
    assert case.config.generator.parse.headers.headers == (
        (case_dir / "headers" / "basic.h").resolve(),
    )
    assert case.config.golden is None


def test_discover_cases_loads_env_include_profile(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """An env-include header case should parse successfully."""
    repo_root = _make_repo_layout(tmp_path)
    case_dir = _make_case(
        repo_root,
        "env_include",
        {
            "schema_version": 2,
            "generator": {
                "lib_id": "fixture_lib",
                "package": "fixture",
                "emit": ["func"],
                "parse": {
                    "headers": {
                        "kind": "env_include",
                        "include_dir_env": "PUREGO_GEN_TEST_INCLUDE_DIR",
                        "headers": ["env_basic.h"],
                    }
                },
            },
        },
    )
    include_dir = case_dir / "external_include"
    include_dir.mkdir(parents=True, exist_ok=True)
    _write_text_line(include_dir / "env_basic.h", "int add(int a, int b);")
    monkeypatch.setenv("PUREGO_GEN_TEST_INCLUDE_DIR", str(include_dir))

    cases = discover_cases(repo_root=repo_root, selected_case_ids=())

    assert len(cases) == 1
    case = cases[0]
    assert isinstance(case.config.generator.parse.headers, EnvIncludeHeaders)
    assert case.config.generator.parse.headers.include_dir_env == "PUREGO_GEN_TEST_INCLUDE_DIR"
    assert case.config.generator.parse.headers.headers == ("env_basic.h",)


def test_discover_cases_defaults_runtime_to_compile_c(tmp_path: Path) -> None:
    """runtime_test.go without explicit runtime should default to compile_c runtime.c."""
    repo_root = _make_repo_layout(tmp_path)
    case_dir = _make_case(
        repo_root,
        "runtime",
        {
            "schema_version": 2,
            "generator": {
                "lib_id": "fixture_lib",
                "package": "fixture",
                "emit": ["func"],
                "parse": {
                    "headers": {
                        "kind": "local",
                        "headers": ["headers/smoke.h"],
                    }
                },
            },
        },
    )
    (case_dir / "headers").mkdir(parents=True, exist_ok=True)
    _write_text_line(case_dir / "headers" / "smoke.h", "int smoke(void);")
    _write_text_line(case_dir / "runtime_test.go", "package fixture")

    cases = discover_cases(repo_root=repo_root, selected_case_ids=())

    runtime = None if cases[0].config.golden is None else cases[0].config.golden.runtime
    assert isinstance(runtime, CompileCRuntime)
    assert runtime.sources == ((case_dir / "runtime.c").resolve(),)
    assert runtime.cflags == ()
    assert runtime.ldflags == ()


def test_resolve_env_libdir_runtime_library_accepts_exact_name(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """env_libdir runtime resolution should pick exact dylib/so names first."""
    runtime = EnvLibdirRuntime(
        lib_dir_env="PUREGO_GEN_TEST_LIB_DIR",
        library_names=("zstd",),
    )
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    library_name = "libzstd.dylib" if sys.platform == "darwin" else "libzstd.so"
    expected_library = lib_dir / library_name
    expected_library.write_text("", encoding="utf-8")
    monkeypatch.setenv("PUREGO_GEN_TEST_LIB_DIR", str(lib_dir))

    resolved = resolve_env_libdir_runtime_library(runtime)

    assert resolved == expected_library.resolve()


def test_load_case_config_formats_validation_errors_with_config_context(tmp_path: Path) -> None:
    """Golden-case config loader should reuse shared validation formatting."""
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "schema_version": 2,
            "generator": {
                "lib_id": "fixture_lib",
                "package": "fixture",
                "emit": ["func"],
                "parse": {
                    "headers": {
                        "kind": "local",
                        "headers": ["headers/basic.h"],
                    }
                },
                "unknown": True,
            },
        },
    )

    with pytest.raises(
        RuntimeError,
        match=r"(?s)config `.*config\.json`.*generator\.unknown.*extra_forbidden",
    ):
        load_case_config(config_path)


def test_load_case_config_resolves_config_path(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Golden-case config loader should record the resolved absolute config path."""
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "schema_version": 2,
            "generator": {
                "lib_id": "fixture_lib",
                "package": "fixture",
                "emit": ["func"],
                "parse": {
                    "headers": {
                        "kind": "local",
                        "headers": ["headers/basic.h"],
                    }
                },
            },
        },
    )
    (tmp_path / "headers").mkdir(parents=True, exist_ok=True)
    _write_text_line(tmp_path / "headers" / "basic.h", "int add(int a, int b);")
    monkeypatch.chdir(tmp_path)

    loaded = load_case_config(Path("config.json"))

    assert loaded.config_path == config_path.resolve()
