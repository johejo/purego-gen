# Copyright (c) 2026 purego-gen contributors.

"""Tests for config filter schema and normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

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
            "parse": {
                "headers": {"kind": "local", "headers": ["basic.h"]},
                "filters": {"func": func_filter},
                "clang_args": [],
            },
            "render": {"type_mapping": {}},
        },
    }


def _config_payload_with_exclude(*, func_exclude: object) -> dict[str, object]:
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    parse = _generator_parse(generator)
    parse["filters"] = {}
    parse["exclude"] = {"func": func_exclude}
    return payload


def _payload_generator(payload: dict[str, object]) -> dict[str, object]:
    generator = payload["generator"]
    assert isinstance(generator, dict)
    return cast("dict[str, object]", generator)


def _generator_parse(generator: dict[str, object]) -> dict[str, object]:
    parse = generator["parse"]
    assert isinstance(parse, dict)
    return cast("dict[str, object]", parse)


def _generator_render(generator: dict[str, object]) -> dict[str, object]:
    render = generator["render"]
    assert isinstance(render, dict)
    return cast("dict[str, object]", render)


def test_build_generator_spec_accepts_regex_string_filter(tmp_path: Path) -> None:
    """String filters should remain regex-backed after normalization."""
    parsed = AppConfigInput.model_validate_json(json.dumps(_config_payload(func_filter="^add$")))

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert spec.parse.filters.func == regex_filter("^add$")


def test_build_generator_spec_defaults_empty_prefixes(tmp_path: Path) -> None:
    """Generator spec should default all naming prefixes to empty string."""
    parsed = AppConfigInput.model_validate_json(json.dumps(_config_payload(func_filter="^add$")))

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert not spec.render.naming.type_prefix
    assert not spec.render.naming.const_prefix
    assert not spec.render.naming.func_prefix
    assert not spec.render.naming.var_prefix


def test_build_generator_spec_accepts_custom_per_kind_prefix(tmp_path: Path) -> None:
    """Generator spec should preserve valid custom per-kind prefixes."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["naming"] = {
        "type_prefix": "purego_gen_",
        "const_prefix": "",
        "func_prefix": "purego_gen_",
        "var_prefix": "purego_gen_",
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert spec.render.naming.type_prefix == "purego_gen_"
    assert not spec.render.naming.const_prefix
    assert spec.render.naming.func_prefix == "purego_gen_"
    assert spec.render.naming.var_prefix == "purego_gen_"


def test_config_schema_accepts_empty_const_prefix() -> None:
    """Constant prefixes should allow an empty string."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["naming"] = {"const_prefix": ""}

    AppConfigInput.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    ("field_name", "prefix_value"),
    [
        ("type_prefix", "purego"),
        ("type_prefix", "purego-gen_"),
        ("type_prefix", "1purego_"),
        ("func_prefix", "purego"),
        ("func_prefix", "purego-gen_"),
        ("func_prefix", "1purego_"),
        ("var_prefix", "purego"),
        ("var_prefix", "purego-gen_"),
        ("var_prefix", "1purego_"),
        ("const_prefix", "purego"),
        ("const_prefix", "purego-gen_"),
        ("const_prefix", "1purego_"),
    ],
)
def test_build_generator_spec_rejects_invalid_identifier_prefix(
    tmp_path: Path,
    field_name: str,
    prefix_value: str,
) -> None:
    """Generator spec should reject invalid generated identifier prefixes."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["naming"] = {field_name: prefix_value}
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))

    with pytest.raises(
        RuntimeError,
        match=rf"generator\.render\.naming\.{field_name} is invalid",
    ):
        build_generator_spec(
            parsed.generator,
            base_dir=tmp_path,
            config_path=tmp_path / "config.json",
        )


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

    assert spec.parse.filters.func == exact_names_filter(("add", "sub"))


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

    assert spec.parse.exclude_filters.func == regex_filter("^reset$")


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

    assert spec.parse.exclude_filters.func == exact_names_filter(("reset",))


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
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["helpers"] = {
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

    assert len(spec.render.helpers.buffer_inputs) == 1
    helper = spec.render.helpers.buffer_inputs[0]
    assert helper.function == "fixture_consume_bytes"
    assert helper.pairs[0].pointer == "data"
    assert helper.pairs[0].length == "data_len"


def test_config_schema_rejects_empty_buffer_input_helper_array() -> None:
    """Helper arrays must contain at least one item when present."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["helpers"] = {"buffer_inputs": []}

    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(json.dumps(payload))


def test_build_generator_spec_accepts_callback_input_helpers(tmp_path: Path) -> None:
    """Callback helper config should normalize into helper models."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["helpers"] = {
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

    assert len(spec.render.helpers.callback_inputs) == 1
    helper = spec.render.helpers.callback_inputs[0]
    assert helper.function == "fixture_register_hook"
    assert helper.parameters == ("callback", "destroy")


def test_build_generator_spec_accepts_header_overlays(tmp_path: Path) -> None:
    """Overlay config should normalize into execution-ready overlay models."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    parse = _generator_parse(generator)
    parse["overlays"] = [
        {
            "path": "virtual.h",
            "content": "int add(int a, int b);\n",
        }
    ]

    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert len(spec.parse.overlays) == 1
    assert spec.parse.overlays[0].path == "virtual.h"
    assert spec.parse.overlays[0].content == "int add(int a, int b);\n"


def test_build_generator_spec_rejects_duplicate_overlay_paths(tmp_path: Path) -> None:
    """Overlay paths must remain unique within one config."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    parse = _generator_parse(generator)
    parse["overlays"] = [
        {"path": "virtual.h", "content": "int add(int a, int b);\n"},
        {"path": "virtual.h", "content": "int reset(void);\n"},
    ]
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))

    with pytest.raises(RuntimeError, match=r"duplicate overlay path: virtual\.h"):
        build_generator_spec(
            parsed.generator,
            base_dir=tmp_path,
            config_path=tmp_path / "config.json",
        )


def test_config_schema_rejects_empty_callback_input_helper_array() -> None:
    """Callback helper arrays must contain at least one item when present."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["helpers"] = {"callback_inputs": []}

    with pytest.raises(ValidationError):
        AppConfigInput.model_validate_json(json.dumps(payload))


def test_build_generator_spec_rejects_helpers_without_func_emit(tmp_path: Path) -> None:
    """Generated helpers require function emission."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    generator["emit"] = "const"
    render = _generator_render(generator)
    render["helpers"] = {
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
            r"generator\.render\.helpers\.buffer_inputs or "
            r"generator\.render\.helpers\.callback_inputs "
            r"requires `func` in generator\.emit"
        ),
    ):
        build_generator_spec(
            parsed.generator,
            base_dir=tmp_path,
            config_path=tmp_path / "config.json",
        )


def test_build_type_mapping_options_defaults_unset_values() -> None:
    """Shared type-mapping helper should apply correct defaults for missing flags."""
    options = build_type_mapping_options(raw_values={"strict_enum_typedefs": True})

    assert options.const_char_as_string is True
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
                "parse": {
                    "headers": {
                        "kind": "local",
                        "headers": ["basic.h"],
                    }
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


def test_build_generator_spec_preserves_per_category_empty_prefix(tmp_path: Path) -> None:
    """Per-category empty prefix should be preserved."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = _generator_render(generator)
    render["naming"] = {
        "type_prefix": "",
        "func_prefix": "",
        "var_prefix": "",
        "const_prefix": "pfx_",
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))

    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    assert not spec.render.naming.type_prefix
    assert not spec.render.naming.func_prefix
    assert not spec.render.naming.var_prefix
    assert spec.render.naming.const_prefix == "pfx_"


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
            "parse": {
                "headers": {"kind": "local", "headers": ["basic.h"]},
                "filters": {"func": ["add"]},
                "exclude": {"type": "^internal_"},
                "clang_args": ["-DTESTING=1"],
            },
            "render": {
                "helpers": {
                    "callback_inputs": [
                        {"function": "fixture_register_hook", "parameters": ["callback"]}
                    ]
                },
                "type_mapping": {"strict_enum_typedefs": True},
            },
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    assert resolved.parse.headers == (str(header_path.resolve()),)
    assert resolved.parse.func_filter == exact_names_filter(("add",))
    assert resolved.parse.type_exclude_filter == regex_filter("^internal_")
    assert resolved.render.helpers.callback_inputs[0].parameters == ("callback",)
    assert not resolved.render.naming.type_prefix
    assert not resolved.render.naming.const_prefix
    assert not resolved.render.naming.func_prefix
    assert not resolved.render.naming.var_prefix
    assert resolved.render.type_mapping.strict_enum_typedefs is True
    assert resolved.parse.clang_args == ("-DTESTING=1",)


def test_resolve_generator_config_preserves_custom_per_kind_prefix(tmp_path: Path) -> None:
    """Resolved execution config should carry custom naming prefixes."""
    header_path = tmp_path / "basic.h"
    header_path.write_text("int add(int a, int b);\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "generator": {
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "parse": {
                "headers": {"kind": "local", "headers": ["basic.h"]},
                "filters": {"func": ["add"]},
            },
            "render": {
                "naming": {
                    "type_prefix": "type_gen_",
                    "const_prefix": "",
                    "func_prefix": "func_gen_",
                    "var_prefix": "var_gen_",
                }
            },
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    assert resolved.render.naming.type_prefix == "type_gen_"
    assert not resolved.render.naming.const_prefix
    assert resolved.render.naming.func_prefix == "func_gen_"
    assert resolved.render.naming.var_prefix == "var_gen_"


def test_resolve_generator_config_resolves_local_overlay_paths_from_config_dir(
    tmp_path: Path,
) -> None:
    """Local overlay paths should resolve relative to the config base dir."""
    payload = {
        "schema_version": 1,
        "generator": {
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "parse": {
                "headers": {"kind": "local", "headers": ["virtual.h"]},
                "overlays": [
                    {
                        "path": "virtual.h",
                        "content": "int add(int a, int b);\n",
                    }
                ],
                "filters": {"func": ["add"]},
            },
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    expected_path = str((tmp_path / "virtual.h").resolve())
    assert resolved.parse.headers == (expected_path,)
    assert resolved.parse.overlays[0].path == expected_path


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
            "parse": {
                "headers": {
                    "kind": "env_include",
                    "include_dir_env": "PUREGO_GEN_INCLUDE_DIR",
                    "headers": ["env_basic.h"],
                },
                "filters": {"const": "^VALUE_"},
                "clang_args": ["-DUSE_ENV=1"],
            },
            "render": {"type_mapping": {"typed_sentinel_constants": True}},
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    assert resolved.parse.headers == (str(header_path.resolve()),)
    assert resolved.parse.const_filter == regex_filter("^VALUE_")
    assert resolved.render.type_mapping.typed_sentinel_constants is True
    assert resolved.parse.clang_args == ("-I", str(include_dir.resolve()), "-DUSE_ENV=1")


def test_resolve_generator_config_resolves_env_include_overlay_paths_from_include_dir(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Env-include overlay paths should resolve relative to the include dir."""
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    monkeypatch.setenv("PUREGO_GEN_INCLUDE_DIR", str(include_dir))
    payload = {
        "schema_version": 1,
        "generator": {
            "lib_id": "fixture_lib",
            "package": "fixture",
            "emit": "func",
            "parse": {
                "headers": {
                    "kind": "env_include",
                    "include_dir_env": "PUREGO_GEN_INCLUDE_DIR",
                    "headers": ["virtual.h"],
                },
                "overlays": [
                    {
                        "path": "virtual.h",
                        "content": "int add(int a, int b);\n",
                    }
                ],
                "filters": {"func": ["add"]},
            },
        },
    }
    parsed = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        parsed.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )

    resolved = resolve_generator_config(spec)

    expected_path = str((include_dir / "virtual.h").resolve())
    assert resolved.parse.headers == (expected_path,)
    assert resolved.parse.overlays[0].path == expected_path


def test_config_schema_accepts_struct_accessors_true() -> None:
    """struct_accessors=true should be accepted in render config."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = cast("dict[str, object]", generator.setdefault("render", {}))
    render["struct_accessors"] = True
    config = AppConfigInput.model_validate_json(json.dumps(payload))
    assert config.generator.render.struct_accessors is True


def test_config_schema_struct_accessors_defaults_false() -> None:
    """struct_accessors should default to False when not specified."""
    payload = _config_payload(func_filter="^add$")
    config = AppConfigInput.model_validate_json(json.dumps(payload))
    assert config.generator.render.struct_accessors is False


def test_config_normalize_passes_struct_accessors_to_render_spec(tmp_path: Path) -> None:
    """struct_accessors=true should propagate through normalization."""
    payload = _config_payload(func_filter="^add$")
    generator = _payload_generator(payload)
    render = cast("dict[str, object]", generator.setdefault("render", {}))
    render["struct_accessors"] = True
    config = AppConfigInput.model_validate_json(json.dumps(payload))
    spec = build_generator_spec(
        config.generator,
        base_dir=tmp_path,
        config_path=tmp_path / "config.json",
    )
    assert spec.render.struct_accessors is True
