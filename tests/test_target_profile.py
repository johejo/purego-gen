# Copyright (c) 2026 purego-gen contributors.

"""Tests for target profile catalog loading/composition."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from purego_gen.target_profile import build_exact_symbol_regex, load_target_profile_catalog

if TYPE_CHECKING:
    from pathlib import Path


def _write_json(path: Path, raw: object) -> None:
    """Write one JSON object to file."""
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_load_target_profile_catalog_applies_compose_order_and_overrides(tmp_path: Path) -> None:
    """Later presets/profile overrides should win with array override semantics."""
    catalog_path = tmp_path / "profiles.json"
    _write_json(
        catalog_path,
        {
            "schema_version": 1,
            "presets": {
                "base": {
                    "header_names": ["zstd.h"],
                    "emit_kinds": "func,type",
                    "required_functions": ["A", "B"],
                    "required_types": ["BaseType"],
                    "type_mapping": {
                        "const_char_as_string": True,
                    },
                },
                "strict_defaults": {
                    "header_names": ["zstd.h", "zstd_errors.h"],
                    "emit_kinds": "func,type,const",
                    "required_types": ["BaseType", "ErrType"],
                    "required_constants": ["ERR_ONE", "ERR_TWO"],
                    "type_mapping": {
                        "strict_enum_typedefs": True,
                    },
                },
            },
            "profiles": {
                "strict_profile": {
                    "compose": ["base", "strict_defaults"],
                    "required_functions": ["A", "B", "C"],
                    "type_mapping": {"typed_sentinel_constants": True},
                }
            },
        },
    )

    profile = load_target_profile_catalog(catalog_path, "strict_profile")
    assert profile.profile_id == "strict_profile"
    assert profile.header_names == ("zstd.h", "zstd_errors.h")
    assert profile.emit_kinds == "func,type,const"
    assert profile.required_functions == ("A", "B", "C")
    assert profile.required_types == ("BaseType", "ErrType")
    assert profile.required_constants == ("ERR_ONE", "ERR_TWO")
    assert profile.function_filter == build_exact_symbol_regex(("A", "B", "C"))
    assert profile.type_filter == build_exact_symbol_regex(("BaseType", "ErrType"))
    assert profile.const_filter == build_exact_symbol_regex(("ERR_ONE", "ERR_TWO"))
    assert profile.type_mapping.const_char_as_string is True
    assert profile.type_mapping.strict_enum_typedefs is True
    assert profile.type_mapping.typed_sentinel_constants is True


def test_load_target_profile_catalog_requires_resolved_header_names(tmp_path: Path) -> None:
    """Profile should fail when composed fields do not provide header_names."""
    catalog_path = tmp_path / "profiles.json"
    _write_json(
        catalog_path,
        {
            "schema_version": 1,
            "presets": {
                "base": {
                    "emit_kinds": "func,type",
                    "required_functions": ["Fn"],
                    "required_types": ["Ty"],
                    "type_mapping": {
                        "const_char_as_string": True,
                    },
                }
            },
            "profiles": {"v1": {"compose": ["base"]}},
        },
    )

    with pytest.raises(RuntimeError, match="must resolve `header_names`"):
        load_target_profile_catalog(catalog_path, "v1")


def test_load_target_profile_catalog_errors_on_unknown_preset(tmp_path: Path) -> None:
    """Unknown preset references should fail with actionable diagnostics."""
    catalog_path = tmp_path / "profiles.json"
    _write_json(
        catalog_path,
        {
            "schema_version": 1,
            "presets": {
                "base": {
                    "emit_kinds": "func,type",
                    "required_functions": ["Fn"],
                    "required_types": ["Ty"],
                    "type_mapping": {
                        "const_char_as_string": True,
                    },
                }
            },
            "profiles": {"v1": {"compose": ["missing_preset"]}},
        },
    )

    with pytest.raises(RuntimeError, match="unknown preset"):
        load_target_profile_catalog(catalog_path, "v1")


def test_load_target_profile_catalog_errors_on_missing_required_fields(tmp_path: Path) -> None:
    """Profile should fail when composed fields do not provide required values."""
    catalog_path = tmp_path / "profiles.json"
    _write_json(
        catalog_path,
        {
            "schema_version": 1,
            "presets": {
                "base": {
                    "required_functions": ["Fn"],
                    "required_types": ["Ty"],
                    "type_mapping": {
                        "const_char_as_string": True,
                    },
                }
            },
            "profiles": {"v1": {"compose": ["base"]}},
        },
    )

    with pytest.raises(RuntimeError, match="must resolve `emit_kinds`"):
        load_target_profile_catalog(catalog_path, "v1")


def test_load_target_profile_catalog_errors_on_unknown_profile_id(tmp_path: Path) -> None:
    """Unknown profile IDs should return available profile identifiers."""
    catalog_path = tmp_path / "profiles.json"
    _write_json(
        catalog_path,
        {
            "schema_version": 1,
            "presets": {
                "base": {
                    "emit_kinds": "func,type",
                    "required_functions": ["Fn"],
                    "required_types": ["Ty"],
                    "type_mapping": {
                        "const_char_as_string": True,
                    },
                }
            },
            "profiles": {"v1": {"compose": ["base"]}},
        },
    )

    with pytest.raises(RuntimeError, match="available profiles: v1"):
        load_target_profile_catalog(catalog_path, "strict")
