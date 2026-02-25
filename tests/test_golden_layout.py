# Copyright (c) 2026 purego-gen contributors.

"""Layout checks for golden output files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOLDEN_DIR = _REPO_ROOT / "tests" / "golden"
_GOLDEN_CASES_PATH = _REPO_ROOT / "scripts" / "golden-cases.json"


def test_no_go_files_directly_under_golden_root() -> None:
    """Golden root should only contain case directories, not `.go` files."""
    root_go_files = sorted(path.name for path in _GOLDEN_DIR.glob("*.go"))
    assert root_go_files == []


def test_golden_manifest_output_paths_follow_case_directory_layout() -> None:
    """Manifest output paths should resolve to `tests/golden/<id>/generated.go`."""
    raw_object = cast("object", json.loads(_GOLDEN_CASES_PATH.read_text(encoding="utf-8")))
    assert isinstance(raw_object, dict)
    raw = cast("dict[str, object]", raw_object)
    cases_object = raw.get("cases")
    assert isinstance(cases_object, list)
    for case_object in cast("list[object]", cases_object):
        assert isinstance(case_object, dict)
        case = cast("dict[str, object]", case_object)
        case_id_object = case.get("id")
        output_path_object = case.get("output_path")
        assert isinstance(case_id_object, str)
        assert case_id_object
        assert isinstance(output_path_object, str)
        assert output_path_object
        expected = f"tests/golden/{case_id_object}/generated.go"
        assert output_path_object == expected
