# Copyright (c) 2026 purego-gen contributors.

"""Target profile catalog loader for harness/script internal workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from purego_gen.config_normalize import build_type_mapping_options
from purego_gen.config_shared import type_mapping_input_to_dict
from purego_gen.declaration_filters import build_exact_symbol_regex
from purego_gen.json_load import load_json_model
from purego_gen.target_profile_schema import (
    CatalogInput,
    ComponentInput,
    ProfileInput,
)

if TYPE_CHECKING:
    from pathlib import Path

    from purego_gen.model import TypeMappingOptions


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


def _load_catalog(path: Path) -> CatalogInput:
    """Load and validate catalog specification.

    Returns:
        Parsed catalog input model.
    """
    return load_json_model(
        path,
        model_type=CatalogInput,
        context=f"target profile catalog `{path.expanduser().resolve()}`",
        missing_label="target profile catalog",
    )


def _merge_component(
    component: ComponentInput,
    *,
    resolved_values: dict[str, object],
    resolved_type_mapping: dict[str, bool],
) -> None:
    if component.header_names is not None:
        resolved_values["header_names"] = component.header_names
    if component.emit_kinds is not None:
        resolved_values["emit_kinds"] = component.emit_kinds
    if component.required_functions is not None:
        resolved_values["required_functions"] = component.required_functions
    if component.required_types is not None:
        resolved_values["required_types"] = component.required_types
    if component.required_constants is not None:
        resolved_values["required_constants"] = component.required_constants
    mapping = type_mapping_input_to_dict(component.type_mapping)
    if mapping is not None:
        resolved_type_mapping.update(mapping)


def _merge_profile_overrides(
    profile: ProfileInput,
    *,
    resolved_values: dict[str, object],
    resolved_type_mapping: dict[str, bool],
) -> None:
    if profile.header_names is not None:
        resolved_values["header_names"] = profile.header_names
    if profile.emit_kinds is not None:
        resolved_values["emit_kinds"] = profile.emit_kinds
    if profile.required_functions is not None:
        resolved_values["required_functions"] = profile.required_functions
    if profile.required_types is not None:
        resolved_values["required_types"] = profile.required_types
    if profile.required_constants is not None:
        resolved_values["required_constants"] = profile.required_constants
    mapping = type_mapping_input_to_dict(profile.type_mapping)
    if mapping is not None:
        resolved_type_mapping.update(mapping)


def _resolve_profile_values(
    *,
    path: Path,
    profile_id: str,
    profile: ProfileInput,
    presets_by_id: dict[str, ComponentInput],
) -> tuple[dict[str, object], dict[str, bool]]:
    resolved_values: dict[str, object] = {}
    resolved_type_mapping: dict[str, bool] = {}

    for compose_id in profile.compose:
        preset = presets_by_id.get(compose_id)
        if preset is None:
            message = (
                f"catalog `{path}` profile `{profile_id}` compose references "
                f"unknown preset `{compose_id}`."
            )
            raise RuntimeError(message)
        _merge_component(
            preset,
            resolved_values=resolved_values,
            resolved_type_mapping=resolved_type_mapping,
        )

    _merge_profile_overrides(
        profile,
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
    return build_type_mapping_options(
        raw_values=resolved_type_mapping,
        require_const_char_as_string=True,
        context=f"catalog `{path}` profile `{profile_id}`",
    )


def load_target_profile_catalog(path: Path, profile_id: str) -> TargetProfile:
    """Load and resolve one profile from a target-profile catalog JSON file.

    Returns:
        Resolved target profile configuration.

    Raises:
        RuntimeError: Profile resolution fails.
    """
    catalog = _load_catalog(path)
    profile = catalog.profiles.get(profile_id)
    if profile is None:
        known_profiles = ", ".join(sorted(catalog.profiles))
        message = (
            f"target profile `{profile_id}` not found in `{path}`. "
            f"available profiles: {known_profiles}"
        )
        raise RuntimeError(message)

    resolved_values, resolved_type_mapping = _resolve_profile_values(
        path=path,
        profile_id=profile_id,
        profile=profile,
        presets_by_id=catalog.presets,
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
