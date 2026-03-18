# Copyright (c) 2026 purego-gen contributors.

"""Tests for config filter schema and normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from purego_gen.config_load import load_app_config, resolve_generator_config
from purego_gen.config_normalize import build_generator_spec, build_type_mapping_options
from purego_gen.config_schema import AppConfigInput
from purego_gen.config_shared import TypeMappingInput, type_mapping_input_to_dict
from purego_gen.declaration_filters import exact_names_filter, regex_filter

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


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


def test_build_generator_spec_accepts_buffer_input_helpers(tmp_path: Path) -> None:
    """Buffer-input helper config should normalize into helper models."""
    payload = _config_payload(func_filter="^add$")
    generator = payload["generator"]
    assert isinstance(generator, dict)
    generator["helpers"] = {
        "buffer_inputs": [
            {
                "function": "fixture_consume_bytes",
                "pairs": [{"pointer": "data", "length": "data_len"}],
            }
        ]
    }

    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert len(spec.helpers.buffer_inputs) == 1
    helper = spec.helpers.buffer_inputs[0]
    assert helper.function == "fixture_consume_bytes"
    assert helper.pairs[0].pointer == "data"
    assert helper.pairs[0].length == "data_len"


def test_config_schema_rejects_empty_buffer_input_helper_array() -> None:
    """Helper arrays must contain at least one item when present."""
    payload = _config_payload(func_filter="^add$")
    generator = payload["generator"]
    assert isinstance(generator, dict)
    generator["helpers"] = {"buffer_inputs": []}

    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(json.dumps(payload))


def test_build_generator_spec_accepts_callback_input_helpers(tmp_path: Path) -> None:
    """Callback helper config should normalize into helper models."""
    payload = _config_payload(func_filter="^add$")
    generator = payload["generator"]
    assert isinstance(generator, dict)
    generator["helpers"] = {
        "callback_inputs": [
            {
                "function": "fixture_register_hook",
                "parameters": ["callback", "destroy"],
            }
        ]
    }

    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert len(spec.helpers.callback_inputs) == 1
    helper = spec.helpers.callback_inputs[0]
    assert helper.function == "fixture_register_hook"
    assert helper.parameters == ("callback", "destroy")


def test_config_schema_rejects_empty_callback_input_helper_array() -> None:
    """Callback helper arrays must contain at least one item when present."""
    payload = _config_payload(func_filter="^add$")
    generator = payload["generator"]
    assert isinstance(generator, dict)
    generator["helpers"] = {"callback_inputs": []}

    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(json.dumps(payload))


def test_build_generator_spec_rejects_helpers_without_func_emit(tmp_path: Path) -> None:
    """Generated helpers require function emission."""
    payload = _config_payload(func_filter="^add$")
    generator = payload["generator"]
    assert isinstance(generator, dict)
    generator["emit"] = "const"
    generator["helpers"] = {
        "callback_inputs": [
            {
                "function": "fixture_register_hook",
                "parameters": ["callback"],
            }
        ]
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))

    with pytest.raises(
        RuntimeError,
        match=(
            r"generator\.helpers\.buffer_inputs or generator\.helpers\.callback_inputs "
            r"requires `func` in generator\.emit"
        ),
    ):
        build_generator_spec(
            parsed.generator,
            base_dir=tmp_path,
            config_path=tmp_path / "config.json",
        )


def test_build_type_mapping_options_defaults_unset_values() -> None:
    """Shared type-mapping helper should default missing flags to false."""
    options = build_type_mapping_options(raw_values={"strict_enum_typedefs": True})

    assert options.const_char_as_string is False
    assert options.strict_enum_typedefs is True
    assert options.typed_sentinel_constants is False


def test_type_mapping_input_to_dict_omits_unset_values() -> None:
    """Sparse type-mapping helper should only emit explicitly configured flags."""
    mapping = type_mapping_input_to_dict(
        TypeMappingInput(strict_enum_typedefs=True, typed_sentinel_constants=None)
    )

    assert mapping == {"strict_enum_typedefs": True}


def test_load_app_config_formats_validation_errors_with_config_context(tmp_path: Path) -> None:
    """Config loader should reuse shared validation formatting."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "schema_version": 1,
            "generator": {
                "lib_id": "fixture_lib",
                "package": "fixture",
                "emit": "func",
                "headers": {
                    "kind": "local",
                    "headers": ["basic.h"],
                },
                "unknown": True,
            },
        }),
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match=r"(?s)config `.*config\.json`.*generator\.unknown.*extra_forbidden",
    ):
        load_app_config(config_path)


def test_load_app_config_resolves_config_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Config loader should record the resolved absolute config path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(_config_payload(func_filter="^add$")),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    loaded = load_app_config(Path("config.json"))

    assert loaded.config_path == config_path.resolve()


def test_resolve_generator_config_preserves_shared_fields_for_local_headers(
    tmp_path: Path,
) -> None:
    """Local header resolution should preserve normalized shared generator fields."""
    header_path = tmp_path / "basic.h"
    header_path.write_text("int add(int a, int b);\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "generator": {
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func,type",
            "headers": {"kind": "local", "headers": ["basic.h"]},
            "filters": {"func": ["add"]},
            "exclude": {"type": "^internal_"},
            "helpers": {
                "callback_inputs": [
                    {"function": "fixture_register_hook", "parameters": ["callback"]}
                ]
            },
            "type_mapping": {"strict_enum_typedefs": True},
            "clang_args": ["-DTESTING=1"],
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    assert resolved.headers == (str(header_path.resolve()),)
    assert resolved.func_filter == exact_names_filter(("add",))
    assert resolved.type_exclude_filter == regex_filter("^internal_")
    assert resolved.helpers.callback_inputs[0].parameters == ("callback",)
    assert resolved.type_mapping.strict_enum_typedefs is True
    assert resolved.clang_args == ("-DTESTING=1",)


def test_resolve_generator_config_preserves_shared_fields_for_env_include_headers(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Env-include resolution should share the same config assembly path."""
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    header_path = include_dir / "env_basic.h"
    header_path.write_text("int add(int a, int b);\n", encoding="utf-8")
    monkeypatch.setenv("PUREGO_GEN_INCLUDE_DIR", str(include_dir))
    payload = {
        "schema_version": 1,
        "generator": {
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func,const",
            "headers": {
                "kind": "env_include",
                "include_dir_env": "PUREGO_GEN_INCLUDE_DIR",
                "headers": ["env_basic.h"],
            },
            "filters": {"const": "^VALUE_"},
            "type_mapping": {"typed_sentinel_constants": True},
            "clang_args": ["-DUSE_ENV=1"],
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    assert resolved.headers == (str(header_path.resolve()),)
    assert resolved.const_filter == regex_filter("^VALUE_")
    assert resolved.type_mapping.typed_sentinel_constants is True
    assert resolved.clang_args == ("-I", str(include_dir.resolve()), "-DUSE_ENV=1")
