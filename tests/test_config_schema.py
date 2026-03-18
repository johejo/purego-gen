# Copyright (c) 2026 purego-gen contributors.

"""Tests for config filter schema and normalization."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from purego_gen.config_normalize import build_generator_spec
from purego_gen.config_schema import AppConfigInput
from purego_gen.declaration_filters import exact_names_filter, regex_filter

if TYPE_CHECKING:
    from pathlib import Path


def _config_payload(*, func_filter: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generator": {
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "headers": {"kind": "local", "headers": ["basic.h"]},
            "filters": {"func": func_filter},
            "type_mapping": {},
            "clang_args": [],
        },
    }


def _config_payload_with_exclude(*, func_exclude: object) -> dict[str, object]:
    payload = _config_payload(func_filter="^add$")
    generator = payload["generator"]
    assert isinstance(generator, dict)
    generator["filters"] = {}
    generator["exclude"] = {"func": func_exclude}
    return payload


def test_build_generator_spec_accepts_regex_string_filter(tmp_path: Path) -> None:
    """String filters should remain regex-backed after normalization."""
    parsed = AppConfigInput.model_validate_json(json.dumps(_config_payload(func_filter="^add$")))

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert spec.filters.func == regex_filter("^add$")


def test_build_generator_spec_accepts_exact_name_array_filter(tmp_path: Path) -> None:
    """Array filters should normalize to exact-name filter specs."""
    parsed = AppConfigInput.model_validate_json(
        json.dumps(_config_payload(func_filter=["add", "sub"]))
    )

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert spec.filters.func == exact_names_filter(("add", "sub"))


def test_config_schema_rejects_empty_filter_array() -> None:
    """Exact-name filter arrays must contain at least one entry."""
    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(json.dumps(_config_payload(func_filter=[])))


def test_config_schema_rejects_empty_filter_name() -> None:
    """Exact-name filter arrays must not contain empty names."""
    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(json.dumps(_config_payload(func_filter=[""])))


def test_build_generator_spec_accepts_regex_string_exclude_filter(tmp_path: Path) -> None:
    """String exclude filters should remain regex-backed after normalization."""
    parsed = AppConfigInput.model_validate_json(
        json.dumps(_config_payload_with_exclude(func_exclude="^reset$"))
    )

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert spec.exclude_filters.func == regex_filter("^reset$")


def test_build_generator_spec_accepts_exact_name_array_exclude_filter(tmp_path: Path) -> None:
    """Array exclude filters should normalize to exact-name filter specs."""
    parsed = AppConfigInput.model_validate_json(
        json.dumps(_config_payload_with_exclude(func_exclude=["reset"]))
    )

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert spec.exclude_filters.func == exact_names_filter(("reset",))


def test_config_schema_rejects_empty_exclude_filter_array() -> None:
    """Exclude exact-name arrays must contain at least one entry."""
    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(
            json.dumps(_config_payload_with_exclude(func_exclude=[]))
        )


def test_config_schema_rejects_empty_exclude_filter_name() -> None:
    """Exclude exact-name arrays must not contain empty names."""
    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(
            json.dumps(_config_payload_with_exclude(func_exclude=[""]))
        )
