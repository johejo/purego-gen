# Copyright (c) 2026 purego-gen contributors.

"""Target profile catalog loader for harness/script internal workflows."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from purego_gen.model import TypeMappingOptions

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_VERSION_V1: Final[int] = 1
_ALLOWED_ROOT_KEYS: Final[frozenset[str]] = frozenset({
    "schema_version",
    "description",
    "presets",
    "profiles",
})
_ALLOWED_COMPONENT_KEYS: Final[frozenset[str]] = frozenset({
    "description",
    "header_names",
    "emit_kinds",
    "required_functions",
    "required_types",
    "required_constants",
    "type_mapping",
})
_ALLOWED_PROFILE_KEYS: Final[frozenset[str]] = _ALLOWED_COMPONENT_KEYS | frozenset({"compose"})
_ALLOWED_TYPE_MAPPING_KEYS: Final[frozenset[str]] = frozenset({
    "const_char_as_string",
    "strict_opaque_handles",
    "strict_enum_typedefs",
    "typed_sentinel_constants",
})


@dataclass(frozen=True, slots=True)
class TargetProfile:
    """Resolved target profile configuration for harness and fixture workflows."""

    profile_id: str
    header_names: tuple[str, ...]
    emit_kinds: str
    required_functions: tuple[str, ...]
    required_types: tuple[str, ...]
    required_constants: tuple[str, ...]
    type_mapping: TypeMappingOptions

    @property
    def function_filter(self) -> str:
        """Return an exact-match regex for required function names."""
        return build_exact_symbol_regex(self.required_functions)

    @property
    def type_filter(self) -> str:
        """Return an exact-match regex for required type names."""
        return build_exact_symbol_regex(self.required_types)

    @property
    def const_filter(self) -> str | None:
        """Return an exact-match regex for required constants, when configured."""
        if not self.required_constants:
            return None
        return build_exact_symbol_regex(self.required_constants)


@dataclass(frozen=True, slots=True)
class _ProfileSpec:
    compose: tuple[str, ...]
    values: dict[str, object]


def build_exact_symbol_regex(symbols: tuple[str, ...]) -> str:
    """Build an exact-match regex that matches only the provided symbols.

    Returns:
        Anchored regular-expression pattern.
    """
    escaped = [re.escape(symbol) for symbol in symbols]
    return "^(" + "|".join(escaped) + ")$"


def _read_non_empty_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        message = f"{context} must be a non-empty string."
        raise TypeError(message)
    return value


def _read_non_empty_string_array(value: object, *, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        message = f"{context} must be a non-empty array."
        raise TypeError(message)

    items: list[str] = []
    for index, element in enumerate(cast("list[object]", value)):
        if not isinstance(element, str) or not element:
            message = f"{context}[{index}] must be a non-empty string."
            raise TypeError(message)
        items.append(element)
    return tuple(items)


def _read_optional_string_array(value: object, *, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    return _read_non_empty_string_array(value, context=context)


def _read_bool(value: object, *, context: str) -> bool:
    if not isinstance(value, bool):
        message = f"{context} must be bool."
        raise TypeError(message)
    return value


def _read_type_mapping(value: object, *, context: str) -> dict[str, bool]:
    if not isinstance(value, dict):
        message = f"{context} must be a JSON object."
        raise TypeError(message)
    raw_mapping = cast("dict[str, object]", value)
    unknown_keys = sorted(set(raw_mapping) - set(_ALLOWED_TYPE_MAPPING_KEYS))
    if unknown_keys:
        message = f"{context} has unsupported key(s): {', '.join(unknown_keys)}"
        raise RuntimeError(message)
    return {key: _read_bool(raw, context=f"{context}.{key}") for key, raw in raw_mapping.items()}


def _read_component(
    raw_component: object,
    *,
    context: str,
    allowed_keys: frozenset[str],
) -> dict[str, object]:
    if not isinstance(raw_component, dict):
        message = f"{context} must be a JSON object."
        raise TypeError(message)
    component = cast("dict[str, object]", raw_component)
    unknown_keys = sorted(set(component) - set(allowed_keys))
    if unknown_keys:
        message = f"{context} has unsupported key(s): {', '.join(unknown_keys)}"
        raise RuntimeError(message)

    normalized: dict[str, object] = {}
    for field_name in ("header_names", "required_functions", "required_types"):
        if field_name in component:
            normalized[field_name] = _read_non_empty_string_array(
                component[field_name],
                context=f"{context}.{field_name}",
            )
    if "required_constants" in component:
        normalized["required_constants"] = _read_optional_string_array(
            component["required_constants"],
            context=f"{context}.required_constants",
        )
    if "emit_kinds" in component:
        normalized["emit_kinds"] = _read_non_empty_string(
            component["emit_kinds"],
            context=f"{context}.emit_kinds",
        )
    if "type_mapping" in component:
        normalized["type_mapping"] = _read_type_mapping(
            component["type_mapping"],
            context=f"{context}.type_mapping",
        )
    return normalized


def _load_catalog_root(path: Path) -> dict[str, object]:
    if not path.is_file():
        message = f"target profile catalog not found: {path}"
        raise RuntimeError(message)
    try:
        raw_object = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        message = f"failed to parse target profile catalog JSON: {error}"
        raise RuntimeError(message) from error
    if not isinstance(raw_object, dict):
        message = f"target profile catalog root must be a JSON object: {path}"
        raise TypeError(message)
    root = cast("dict[str, object]", raw_object)
    unknown_keys = sorted(set(root) - set(_ALLOWED_ROOT_KEYS))
    if unknown_keys:
        message = f"target profile catalog has unsupported key(s): {', '.join(unknown_keys)}"
        raise RuntimeError(message)

    schema_version = root.get("schema_version")
    if not isinstance(schema_version, int):
        message = f"target profile catalog must define int `schema_version`: {path}"
        raise TypeError(message)
    if schema_version != _SCHEMA_VERSION_V1:
        message = (
            f"unsupported target profile catalog schema_version={schema_version}. "
            f"expected {_SCHEMA_VERSION_V1}."
        )
        raise RuntimeError(message)
    return root


def _read_presets(path: Path, raw_presets: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw_presets, dict) or not raw_presets:
        message = f"target profile catalog `{path}` must define non-empty object `presets`."
        raise RuntimeError(message)
    presets_by_id: dict[str, dict[str, object]] = {}
    for preset_id, raw_preset in cast("dict[str, object]", raw_presets).items():
        normalized_preset_id = _read_non_empty_string(
            preset_id,
            context=f"catalog `{path}` preset id",
        )
        presets_by_id[normalized_preset_id] = _read_component(
            raw_preset,
            context=f"catalog `{path}` preset `{normalized_preset_id}`",
            allowed_keys=_ALLOWED_COMPONENT_KEYS,
        )
    return presets_by_id


def _read_profiles(path: Path, raw_profiles: object) -> dict[str, _ProfileSpec]:
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        message = f"target profile catalog `{path}` must define non-empty object `profiles`."
        raise RuntimeError(message)
    profiles_by_id: dict[str, _ProfileSpec] = {}
    for raw_profile_id, raw_profile in cast("dict[str, object]", raw_profiles).items():
        normalized_profile_id = _read_non_empty_string(
            raw_profile_id,
            context=f"catalog `{path}` profile id",
        )
        component = _read_component(
            raw_profile,
            context=f"catalog `{path}` profile `{normalized_profile_id}`",
            allowed_keys=_ALLOWED_PROFILE_KEYS,
        )
        if not isinstance(raw_profile, dict):
            message = f"catalog `{path}` profile `{normalized_profile_id}` must be JSON object."
            raise TypeError(message)
        compose = _read_non_empty_string_array(
            cast("dict[str, object]", raw_profile).get("compose"),
            context=f"catalog `{path}` profile `{normalized_profile_id}`.compose",
        )
        profiles_by_id[normalized_profile_id] = _ProfileSpec(compose=compose, values=component)
    return profiles_by_id


def _merge_component_values(
    component: dict[str, object],
    *,
    resolved_values: dict[str, object],
    resolved_type_mapping: dict[str, bool],
) -> None:
    for key, value in component.items():
        if key == "type_mapping":
            resolved_type_mapping.update(cast("dict[str, bool]", value))
            continue
        resolved_values[key] = value


def _resolve_profile_values(
    *,
    path: Path,
    profile_id: str,
    profile_spec: _ProfileSpec,
    presets_by_id: dict[str, dict[str, object]],
) -> tuple[dict[str, object], dict[str, bool]]:
    resolved_values: dict[str, object] = {}
    resolved_type_mapping: dict[str, bool] = {}

    for compose_id in profile_spec.compose:
        preset = presets_by_id.get(compose_id)
        if preset is None:
            message = (
                f"catalog `{path}` profile `{profile_id}` compose references "
                f"unknown preset `{compose_id}`."
            )
            raise RuntimeError(message)
        _merge_component_values(
            preset,
            resolved_values=resolved_values,
            resolved_type_mapping=resolved_type_mapping,
        )

    _merge_component_values(
        profile_spec.values,
        resolved_values=resolved_values,
        resolved_type_mapping=resolved_type_mapping,
    )
    return resolved_values, resolved_type_mapping


def _require_resolved_value(
    *,
    path: Path,
    profile_id: str,
    key: str,
    resolved_values: dict[str, object],
) -> object:
    value = resolved_values.get(key)
    if value is None:
        message = f"catalog `{path}` profile `{profile_id}` must resolve `{key}`."
        raise RuntimeError(message)
    return value


def _build_type_mapping(
    *,
    path: Path,
    profile_id: str,
    resolved_type_mapping: dict[str, bool],
) -> TypeMappingOptions:
    if "const_char_as_string" not in resolved_type_mapping:
        message = (
            f"catalog `{path}` profile `{profile_id}` must resolve "
            "`type_mapping.const_char_as_string`."
        )
        raise RuntimeError(message)
    if "strict_opaque_handles" not in resolved_type_mapping:
        message = (
            f"catalog `{path}` profile `{profile_id}` must resolve "
            "`type_mapping.strict_opaque_handles`."
        )
        raise RuntimeError(message)
    return TypeMappingOptions(
        const_char_as_string=resolved_type_mapping["const_char_as_string"],
        strict_opaque_handles=resolved_type_mapping["strict_opaque_handles"],
        strict_enum_typedefs=resolved_type_mapping.get("strict_enum_typedefs", False),
        typed_sentinel_constants=resolved_type_mapping.get("typed_sentinel_constants", False),
    )


def load_target_profile_catalog(path: Path, profile_id: str) -> TargetProfile:
    """Load and resolve one profile from a target-profile catalog JSON file.

    Returns:
        Resolved target profile.

    Raises:
        RuntimeError: Catalog/profile/preset resolution fails.
    """
    root = _load_catalog_root(path)
    presets_by_id = _read_presets(path, root.get("presets"))
    profiles_by_id = _read_profiles(path, root.get("profiles"))
    profile_spec = profiles_by_id.get(profile_id)
    if profile_spec is None:
        known_profiles = ", ".join(sorted(profiles_by_id))
        message = (
            f"target profile `{profile_id}` not found in `{path}`. "
            f"available profiles: {known_profiles}"
        )
        raise RuntimeError(message)

    resolved_values, resolved_type_mapping = _resolve_profile_values(
        path=path,
        profile_id=profile_id,
        profile_spec=profile_spec,
        presets_by_id=presets_by_id,
    )

    emit_kinds = _require_resolved_value(
        path=path,
        profile_id=profile_id,
        key="emit_kinds",
        resolved_values=resolved_values,
    )
    header_names = _require_resolved_value(
        path=path,
        profile_id=profile_id,
        key="header_names",
        resolved_values=resolved_values,
    )
    required_functions = _require_resolved_value(
        path=path,
        profile_id=profile_id,
        key="required_functions",
        resolved_values=resolved_values,
    )
    required_types = _require_resolved_value(
        path=path,
        profile_id=profile_id,
        key="required_types",
        resolved_values=resolved_values,
    )

    return TargetProfile(
        profile_id=profile_id,
        header_names=cast("tuple[str, ...]", header_names),
        emit_kinds=cast("str", emit_kinds),
        required_functions=cast("tuple[str, ...]", required_functions),
        required_types=cast("tuple[str, ...]", required_types),
        required_constants=cast("tuple[str, ...]", resolved_values.get("required_constants", ())),
        type_mapping=_build_type_mapping(
            path=path,
            profile_id=profile_id,
            resolved_type_mapping=resolved_type_mapping,
        ),
    )
