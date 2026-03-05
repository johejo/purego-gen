# Copyright (c) 2026 purego-gen contributors.

"""Tests for case-driven golden profile loading and validation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from golden_cases_lib import CompileCRuntime, LocalHeaders, discover_cases

if TYPE_CHECKING:
    from pathlib import Path


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
    """Create one case directory with profile and placeholder generated.go.

    Returns:
        Created case directory path.
    """
    case_dir = repo_root / "tests" / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_json(case_dir / "profile.json", profile)
    _write_text_line(case_dir / "generated.go", "package fixture")
    return case_dir


def test_discover_cases_loads_local_profile(tmp_path: Path) -> None:
    """A minimal local-header case should parse successfully."""
    repo_root = _make_repo_layout(tmp_path)
    case_dir = _make_case(
        repo_root,
        "one",
        {
            "schema_version": 1,
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {
                "kind": "local",
                "paths": ["headers/basic.h"],
            },
        },
    )
    (case_dir / "headers").mkdir(parents=True, exist_ok=True)
    _write_text_line(case_dir / "headers" / "basic.h", "int add(int a, int b);")

    cases = discover_cases(repo_root=repo_root, selected_case_ids=())

    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "one"
    assert isinstance(case.profile.headers, LocalHeaders)
    assert case.profile.headers.paths == ("headers/basic.h",)
    assert case.profile.runtime is None


def test_discover_cases_defaults_runtime_to_compile_c(tmp_path: Path) -> None:
    """runtime_test.go without explicit runtime should default to compile_c runtime.c."""
    repo_root = _make_repo_layout(tmp_path)
    case_dir = _make_case(
        repo_root,
        "runtime",
        {
            "schema_version": 1,
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {
                "kind": "local",
                "paths": ["headers/smoke.h"],
            },
        },
    )
    (case_dir / "headers").mkdir(parents=True, exist_ok=True)
    _write_text_line(case_dir / "headers" / "smoke.h", "int smoke(void);")
    _write_text_line(case_dir / "runtime_test.go", "package fixture")

    cases = discover_cases(repo_root=repo_root, selected_case_ids=())

    runtime = cases[0].profile.runtime
    assert isinstance(runtime, CompileCRuntime)
    assert runtime.sources == ("runtime.c",)
    assert runtime.cflags == ()
    assert runtime.ldflags == ()


def test_discover_cases_rejects_unknown_profile_key(tmp_path: Path) -> None:
    """Unknown top-level keys should fail with actionable diagnostics."""
    repo_root = _make_repo_layout(tmp_path)
    _make_case(
        repo_root,
        "bad",
        {
            "schema_version": 1,
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {
                "kind": "local",
                "paths": ["headers/basic.h"],
            },
            "unknown": True,
        },
    )

    with pytest.raises(RuntimeError, match=r"unknown.*extra_forbidden"):
        discover_cases(repo_root=repo_root, selected_case_ids=())


def test_discover_cases_rejects_compile_c_without_sources(tmp_path: Path) -> None:
    """compile_c runtime must define non-empty sources."""
    repo_root = _make_repo_layout(tmp_path)
    _make_case(
        repo_root,
        "bad_runtime",
        {
            "schema_version": 1,
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {
                "kind": "local",
                "paths": ["headers/basic.h"],
            },
            "runtime": {
                "kind": "compile_c",
                "cflags": ["-Wall"],
            },
        },
    )

    with pytest.raises(RuntimeError, match=r"runtime\.compile_c\.sources.*missing"):
        discover_cases(repo_root=repo_root, selected_case_ids=())


def test_discover_cases_rejects_unknown_runtime_kind(tmp_path: Path) -> None:
    """Unknown runtime discriminator values should fail in validation."""
    repo_root = _make_repo_layout(tmp_path)
    _make_case(
        repo_root,
        "bad_runtime_kind",
        {
            "schema_version": 1,
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {
                "kind": "local",
                "paths": ["headers/basic.h"],
            },
            "runtime": {
                "kind": "unknown_runtime",
            },
        },
    )

    with pytest.raises(RuntimeError, match=r"runtime.*union_tag_invalid"):
        discover_cases(repo_root=repo_root, selected_case_ids=())


def test_discover_cases_rejects_non_bool_header_flag(tmp_path: Path) -> None:
    """String bools should not be coerced for strict header config flags."""
    repo_root = _make_repo_layout(tmp_path)
    _make_case(
        repo_root,
        "bad_bool",
        {
            "schema_version": 1,
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {
                "kind": "pkg_config",
                "package": "libzstd",
                "header_names": ["zstd.h"],
                "use_cflags": "true",
            },
        },
    )

    with pytest.raises(RuntimeError, match=r"headers\.pkg_config\.use_cflags.*bool_type"):
        discover_cases(repo_root=repo_root, selected_case_ids=())
