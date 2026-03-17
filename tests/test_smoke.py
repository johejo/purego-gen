# Copyright (c) 2026 purego-gen contributors.

"""CLI smoke tests focused on failures and interface boundaries."""

from __future__ import annotations

import os
import sys
from json import dumps
from pathlib import Path
from typing import cast

import pytest

from purego_gen.diagnostics import (
    OPAQUE_DIAGNOSTIC_CODE_EMITTED_COUNT,
    OPAQUE_DIAGNOSTIC_CODE_FALLBACK_COUNT,
)
from purego_gen.model import (
    TYPE_DIAGNOSTIC_CODE_NO_SUPPORTED_FIELDS,
    TYPE_DIAGNOSTIC_CODE_UNSUPPORTED_BITFIELD,
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

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | JsonArray | JsonObject
type JsonArray = list[JsonValue]
type JsonObject = dict[str, JsonValue]


def _write_config(
    tmp_path: Path,
    *,
    generator_overrides: JsonObject,
) -> Path:
    config_path = tmp_path / "config.json"
    generator: JsonObject = {
        "lib_id": _FIXTURE_LIB_ID,
        "package": _FIXTURE_PACKAGE,
        "emit": "func",
        "headers": {"kind": "local", "headers": [str(_PRIMARY_HEADER)]},
        "filters": {},
        "type_mapping": {},
        "clang_args": [],
    }
    generator.update(generator_overrides)
    config_path.write_text(
        dumps(
            {
                "schema_version": 1,
                "generator": generator,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path


def _json_object(value: JsonObject) -> JsonObject:
    return value


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


def test_reports_skipped_typedef_diagnostics_for_unsupported_record_fields(tmp_path: Path) -> None:
    """CLI should report skipped typedef diagnostics for unsupported record patterns."""
    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {"kind": "local", "headers": [str(_ABI_TYPES_HEADER)]},
                    "emit": "type,const",
                }),
            )
        ),
    )

    assert result.returncode == 0
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


def test_fails_when_header_has_parse_errors(tmp_path: Path) -> None:
    """Invalid C headers should fail fast with parse diagnostics."""
    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {"kind": "local", "headers": [str(_BROKEN_HEADER)]},
                }),
            )
        ),
    )

    assert result.returncode == 1
    assert "failed to parse" in result.stderr


@pytest.mark.parametrize(
    ("header_path", "emit_kind", "filters"),
    [
        pytest.param(_PRIMARY_HEADER, "func", {"func": "^does_not_exist$"}, id="func"),
        pytest.param(_ABI_TYPES_HEADER, "type", {"type": "^does_not_exist$"}, id="type"),
        pytest.param(_CATEGORY_HEADER, "const", {"const": "^does_not_exist$"}, id="const"),
        pytest.param(_CATEGORY_HEADER, "var", {"var": "^does_not_exist$"}, id="var"),
    ],
)
def test_fails_when_filter_matches_no_emitted_declarations(
    tmp_path: Path,
    header_path: Path,
    emit_kind: str,
    filters: dict[str, str],
) -> None:
    """Config filters should fail when they match no declaration in emitted categories."""
    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {"kind": "local", "headers": [str(header_path)]},
                    "emit": emit_kind,
                    "filters": cast("JsonObject", filters),
                }),
            )
        ),
    )
    assert result.returncode == 1
    filter_name = next(iter(filters))
    assert f"no declarations matched --{filter_name}-filter: ^does_not_exist$" in result.stderr


def test_accepts_exact_name_array_filters_in_config(tmp_path: Path) -> None:
    """Config array filters should behave as exact-name declaration filters."""
    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {"kind": "local", "headers": [str(_PRIMARY_HEADER)]},
                    "emit": "func",
                    "filters": {"func": ["add"]},
                }),
            )
        ),
    )

    assert result.returncode == 0, result.stderr
    assert "purego_func_add" in result.stdout
    assert "purego_func_reset" not in result.stdout


def test_exact_name_array_filter_no_match_reports_original_value(tmp_path: Path) -> None:
    """No-match failures should show the original exact-name array value."""
    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {"kind": "local", "headers": [str(_PRIMARY_HEADER)]},
                    "emit": "func",
                    "filters": {"func": ["does_not_exist"]},
                }),
            )
        ),
    )

    assert result.returncode == 1
    assert 'no declarations matched --func-filter: ["does_not_exist"]' in result.stderr


def test_does_not_fail_when_filter_targets_non_emitted_category(tmp_path: Path) -> None:
    """Config filters outside `emit` should not trigger no-match failures."""
    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {"kind": "local", "headers": [str(_CATEGORY_HEADER)]},
                    "filters": {"const": "^does_not_exist$"},
                }),
            )
        ),
    )
    assert result.returncode == 0
    assert _REGISTER_FUNCTIONS_SYMBOL in result.stdout


def test_env_include_headers_work_from_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config env-backed headers should resolve during generation."""
    include_dir = tmp_path / "include"
    include_dir.mkdir(parents=True, exist_ok=True)
    (include_dir / "basic.h").write_text(
        _PRIMARY_HEADER.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("PUREGO_GEN_TEST_INCLUDE_DIR", str(include_dir))

    result = _run_cli(
        "--config",
        str(
            _write_config(
                tmp_path,
                generator_overrides=_json_object({
                    "headers": {
                        "kind": "env_include",
                        "include_dir_env": "PUREGO_GEN_TEST_INCLUDE_DIR",
                        "headers": ["basic.h"],
                    },
                }),
            )
        ),
    )

    assert result.returncode == 0
    assert _REGISTER_FUNCTIONS_SYMBOL in result.stdout
