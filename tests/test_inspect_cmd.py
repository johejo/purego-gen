# Copyright (c) 2026 purego-gen contributors.

"""Tests for ``purego-gen inspect`` subcommand."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from purego_gen.process_exec import CommandResult, run_command

from .helper.stdout_assertions import assert_text_contains_fragments

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"


def _run_inspect(*args: str) -> CommandResult:
    """Run ``purego-gen inspect`` via subprocess for end-to-end behavior checks.

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
        [sys.executable, "-m", "purego_gen", "inspect", *args],
        cwd=_REPO_ROOT,
        env=env,
    )


def test_inspect_exits_zero_for_local_fixture_header() -> None:
    """Inspect subcommand should complete successfully for local fixture header."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "basic.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--sample-size",
        "0",
    )
    assert result.returncode == 0, result.stderr
    assert_text_contains_fragments(
        result.stdout,
        (
            "package=manual",
            "opaque_record_typedefs=",
            "sample_opaque_record_typedefs:",
        ),
    )


def test_inspect_reports_callback_candidates() -> None:
    """Inspect should report functions with function-pointer parameters."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "callback_candidates.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--sample-size",
        "10",
    )
    assert result.returncode == 0, result.stderr
    assert_text_contains_fragments(
        result.stdout,
        (
            "callback_candidates=",
            "sample_callback_candidates:",
            "register_handler:",
            "set_callback:",
            "multi_callback:",
        ),
    )
    # Control function with no function-pointer params should NOT appear in candidates
    lines = result.stdout.splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.startswith("sample_callback_candidates:")
    )
    candidate_lines = [line for i, line in enumerate(lines) if i > start and line.startswith("  ")]
    candidate_func_names = [line.split(":")[0].strip() for line in candidate_lines]
    assert "plain_add" not in candidate_func_names


def test_inspect_emit_callback_config_outputs_json() -> None:
    """--emit-callback-config should output a callback_inputs JSON snippet."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "callback_candidates.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--sample-size",
        "0",
        "--emit-callback-config",
    )
    assert result.returncode == 0, result.stderr
    assert_text_contains_fragments(
        result.stdout,
        (
            "callback_inputs:",
            '"function"',
            '"parameters"',
            '"register_handler"',
            '"set_callback"',
            '"multi_callback"',
        ),
    )


def test_inspect_reports_callback_registration_patterns() -> None:
    """Inspect should report detected callback registration patterns."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "callback_candidates.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--sample-size",
        "10",
    )
    assert result.returncode == 0, result.stderr
    assert_text_contains_fragments(
        result.stdout,
        (
            "callback_registration_patterns=",
            "sample_callback_registration_patterns:",
        ),
    )


def test_inspect_exclude_filters() -> None:
    """--func-exclude should remove matching functions from output."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "basic.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--func-exclude",
        "add",
        "--list-names",
    )
    assert result.returncode == 0, result.stderr
    # The exclude filter should remove functions matching "add"
    lines = result.stdout.splitlines()
    func_start = next(i for i, line in enumerate(lines) if line == "functions:")
    func_names: list[str] = []
    for line in lines[func_start + 1 :]:
        if line.startswith("  "):
            func_names.append(line.strip())
        else:
            break
    assert len(func_names) > 0, "should have at least one function remaining"
    for name in func_names:
        assert "add" not in name.lower(), f"excluded function found: {name}"


def test_inspect_list_names() -> None:
    """--list-names should output sorted declaration names by category."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "basic.h"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--list-names",
    )
    assert result.returncode == 0, result.stderr
    assert_text_contains_fragments(
        result.stdout,
        ("functions:",),
    )
    # Names should be sorted within each category
    lines = result.stdout.splitlines()
    func_start = next(i for i, line in enumerate(lines) if line == "functions:")
    func_names: list[str] = []
    for line in lines[func_start + 1 :]:
        if line.startswith("  "):
            func_names.append(line.strip())
        else:
            break
    assert func_names == sorted(func_names), "function names should be sorted"
    assert len(func_names) > 0, "should have at least one function"


def test_inspect_include_and_exclude_combined() -> None:
    """Include and exclude filters should work together."""
    header_path = _REPO_ROOT / "tests" / "fixtures" / "basic.h"
    # Include all functions, then exclude those matching "add"
    result = _run_inspect(
        "--header-path",
        str(header_path),
        "--func-filter",
        ".*",
        "--func-exclude",
        "add",
        "--list-names",
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    func_start = next(i for i, line in enumerate(lines) if line == "functions:")
    func_names: list[str] = []
    for line in lines[func_start + 1 :]:
        if line.startswith("  "):
            func_names.append(line.strip())
        else:
            break
    assert len(func_names) > 0, "should have at least one function remaining"
    for name in func_names:
        assert "add" not in name.lower(), f"excluded function found: {name}"
