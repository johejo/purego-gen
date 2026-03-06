# Copyright (c) 2026 purego-gen contributors.

"""CLI smoke tests focused on failures and interface boundaries."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from purego_gen.diagnostics import (
    OPAQUE_DIAGNOSTIC_CODE_EMITTED_COUNT,
    OPAQUE_DIAGNOSTIC_CODE_FALLBACK_COUNT,
)
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF,
)
from purego_gen.process_exec import CommandResult, run_command

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_FIXTURE_LIB_ID = "fixture_lib"
_FIXTURE_PACKAGE = "fixture"
_REGISTER_FUNCTIONS_SYMBOL = f"purego_{_FIXTURE_LIB_ID}_register_functions"
_NO_SUPPORTED_FIELDS_DIAGNOSTIC_COUNT = 1

_PRIMARY_HEADER = _FIXTURES_DIR / "basic.h"
_CATEGORY_HEADER = _FIXTURES_DIR / "categories.h"
_ABI_TYPES_HEADER = _FIXTURES_DIR / "abi_types.h"
_BROKEN_HEADER = _FIXTURES_DIR / "broken_header.h"


def _run_cli(*args: str) -> CommandResult:
    """Run the CLI via module execution for end-to-end smoke checks.

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
        [sys.executable, "-m", "purego_gen", *args],
        cwd=_REPO_ROOT,
        env=env,
    )


def test_help() -> None:
    """`--help` should succeed and expose top-level usage."""
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "usage: purego-gen" in result.stdout


def test_reports_skipped_typedef_diagnostics_for_unsupported_record_fields() -> None:
    """CLI should report skipped typedef diagnostics for unsupported record patterns."""
    result = _run_cli(
        "--lib-id",
        _FIXTURE_LIB_ID,
        "--header",
        str(_ABI_TYPES_HEADER),
        "--pkg",
        _FIXTURE_PACKAGE,
        "--emit",
        "type,const",
    )

    assert result.returncode == 0
    assert "skipped typedef fixture_with_array_t" in result.stderr
    assert f"[{TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_FIELD_TYPE}]" in result.stderr
    assert "skipped typedef fixture_union_t" in result.stderr
    assert f"[{TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_UNION_TYPEDEF}]" in result.stderr
    assert "skipped typedef fixture_with_bitfield_t" in result.stderr
    assert f"[{TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD}]" in result.stderr
    assert "skipped typedef fixture_with_anonymous_field_t" in result.stderr
    assert (
        result.stderr.count(f"[{TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS}]")
        == _NO_SUPPORTED_FIELDS_DIAGNOSTIC_COUNT
    )
    assert f"[{OPAQUE_DIAGNOSTIC_CODE_EMITTED_COUNT}]: 1" in result.stderr
    assert f"[{OPAQUE_DIAGNOSTIC_CODE_FALLBACK_COUNT}]: 0" in result.stderr


def test_fails_when_header_has_parse_errors() -> None:
    """Invalid C headers should fail fast with parse diagnostics."""
    result = _run_cli(
        "--lib-id",
        _FIXTURE_LIB_ID,
        "--header",
        str(_BROKEN_HEADER),
        "--pkg",
        _FIXTURE_PACKAGE,
        "--emit",
        "func",
    )

    assert result.returncode == 1
    assert "failed to parse" in result.stderr


@pytest.mark.parametrize(
    ("header_path", "emit_kind", "filter_option"),
    [
        pytest.param(_PRIMARY_HEADER, "func", "--func-filter", id="func"),
        pytest.param(_ABI_TYPES_HEADER, "type", "--type-filter", id="type"),
        pytest.param(_CATEGORY_HEADER, "const", "--const-filter", id="const"),
        pytest.param(_CATEGORY_HEADER, "var", "--var-filter", id="var"),
    ],
)
def test_fails_when_filter_matches_no_emitted_declarations(
    header_path: Path,
    emit_kind: str,
    filter_option: str,
) -> None:
    """Filters should fail when they match no declaration in emitted categories."""
    result = _run_cli(
        "--lib-id",
        _FIXTURE_LIB_ID,
        "--header",
        str(header_path),
        "--pkg",
        _FIXTURE_PACKAGE,
        "--emit",
        emit_kind,
        filter_option,
        "^does_not_exist$",
    )
    assert result.returncode == 1
    assert f"no declarations matched {filter_option}: ^does_not_exist$" in result.stderr


def test_does_not_fail_when_filter_targets_non_emitted_category() -> None:
    """Filters for categories outside `--emit` should not trigger no-match failures."""
    result = _run_cli(
        "--lib-id",
        _FIXTURE_LIB_ID,
        "--header",
        str(_CATEGORY_HEADER),
        "--pkg",
        _FIXTURE_PACKAGE,
        "--emit",
        "func",
        "--const-filter",
        "^does_not_exist$",
    )
    assert result.returncode == 0
    assert _REGISTER_FUNCTIONS_SYMBOL in result.stdout
