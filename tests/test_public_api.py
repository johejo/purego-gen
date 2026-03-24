# Copyright (c) 2026 purego-gen contributors.

"""Tests for public API glue code generation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from purego_gen.config_normalize import normalize_public_api
from purego_gen.config_schema import PatternInput, PublicApiInput


def _parse(raw: object) -> PublicApiInput:
    return PublicApiInput.model_validate_json(json.dumps(raw))


def test_public_api_schema_minimal_type_aliases() -> None:
    """Minimal type_aliases config should parse successfully."""
    config = _parse({"type_aliases": {"include": ["sqlite3", "sqlite3_stmt"]}})
    assert config.type_aliases is not None
    assert config.type_aliases.include == ("sqlite3", "sqlite3_stmt")


def test_public_api_schema_with_pattern() -> None:
    """Pattern-based include items should parse successfully."""
    config = _parse({
        "wrappers": {
            "include": ["sqlite3_malloc", {"pattern": "sqlite3_bind_.*"}],
        }
    })
    assert config.wrappers is not None
    assert config.wrappers.include[0] == "sqlite3_malloc"
    assert isinstance(config.wrappers.include[1], PatternInput)
    assert config.wrappers.include[1].pattern == "sqlite3_bind_.*"


def test_public_api_schema_full() -> None:
    """Full public_api config with all fields should parse successfully."""
    config = _parse({
        "strip_prefix": "sqlite3_",
        "type_aliases": {
            "include": ["sqlite3", "sqlite3_stmt"],
            "exclude": ["sqlite3_value"],
            "overrides": {"sqlite3": "DB"},
        },
        "wrappers": {
            "include": ["sqlite3_malloc", {"pattern": "sqlite3_bind_.*"}],
            "exclude": ["sqlite3_bind_pointer"],
            "overrides": {"sqlite3_db_release_memory": "DBReleaseMemory"},
        },
    })
    assert config.strip_prefix == "sqlite3_"
    assert config.type_aliases is not None
    assert config.wrappers is not None


def test_public_api_schema_rejects_empty_include() -> None:
    """Empty include list should fail validation."""
    with pytest.raises(ValidationError):
        _parse({"type_aliases": {"include": []}})


def test_public_api_schema_rejects_extra_fields() -> None:
    """Extra fields should be rejected by strict mode."""
    with pytest.raises(ValidationError):
        _parse({"type_aliases": {"include": ["foo"], "unknown": True}})


def test_normalize_public_api_none_returns_none() -> None:
    """None input should return None."""
    assert normalize_public_api(None, lib_id="mylib") is None


def test_normalize_public_api_default_strip_prefix() -> None:
    """Missing strip_prefix should default to lib_id + '_'."""
    config = _parse({"type_aliases": {"include": ["mylib_db"]}})
    spec = normalize_public_api(config, lib_id="mylib")
    assert spec is not None
    assert spec.strip_prefix == "mylib_"


def test_normalize_public_api_explicit_strip_prefix() -> None:
    """Explicit strip_prefix should be used."""
    config = _parse({
        "strip_prefix": "sqlite3_",
        "type_aliases": {"include": ["sqlite3_db"]},
    })
    spec = normalize_public_api(config, lib_id="sqlite3")
    assert spec is not None
    assert spec.strip_prefix == "sqlite3_"


def test_normalize_public_api_compiles_filters() -> None:
    """Normalization should compile include/exclude into regex patterns."""
    config = _parse({
        "wrappers": {
            "include": ["mylib_malloc", {"pattern": "mylib_bind_.*"}],
            "exclude": ["mylib_bind_pointer"],
        }
    })
    spec = normalize_public_api(config, lib_id="mylib")
    assert spec is not None
    assert spec.wrappers_config is not None
    assert spec.wrappers_config.include.search("mylib_malloc") is not None
    assert spec.wrappers_config.include.search("mylib_bind_int") is not None
    assert spec.wrappers_config.include.search("mylib_free") is None
    assert spec.wrappers_config.exclude is not None
    assert spec.wrappers_config.exclude.search("mylib_bind_pointer") is not None


def test_normalize_public_api_preserves_overrides() -> None:
    """Overrides should be preserved in the normalized spec."""
    config = _parse({
        "type_aliases": {
            "include": ["mylib_db"],
            "overrides": {"mylib_db": "DB"},
        }
    })
    spec = normalize_public_api(config, lib_id="mylib")
    assert spec is not None
    assert spec.type_aliases_config is not None
    assert spec.type_aliases_config.overrides == {"mylib_db": "DB"}


def test_normalize_public_api_rejects_invalid_override_value() -> None:
    """Override values that are not valid Go identifiers should be rejected."""
    config = _parse({
        "type_aliases": {
            "include": ["mylib_db"],
            "overrides": {"mylib_db": "123bad"},
        }
    })
    with pytest.raises(RuntimeError, match="not a valid Go identifier"):
        normalize_public_api(config, lib_id="mylib")


def test_normalize_public_api_pattern_only_include() -> None:
    """Include list with only patterns (no explicit names) should normalize."""
    config = _parse({
        "wrappers": {
            "include": [{"pattern": "mylib_.*"}],
        }
    })
    spec = normalize_public_api(config, lib_id="mylib")
    assert spec is not None
    assert spec.wrappers_config is not None
    assert spec.wrappers_config.include.search("mylib_open") is not None
    assert spec.wrappers_config.include.search("other_func") is None
