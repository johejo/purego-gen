# Copyright (c) 2026 purego-gen contributors.

"""Pure normalization helpers for shared generator config."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from purego_gen.config_model import (
    EnvIncludeHeaders,
    GeneratorFilters,
    GeneratorNaming,
    GeneratorParseSpec,
    GeneratorRenderSpec,
    GeneratorSpec,
    HeaderConfig,
    LocalHeaders,
)
from purego_gen.config_schema import (
    FiltersInput,
    GeneratorInput,
    LocalHeadersInput,
    TypeMappingInput,
)
from purego_gen.declaration_filters import FilterSpec, exact_names_filter, regex_filter
from purego_gen.emit_kinds import parse_emit_kinds
from purego_gen.helper_config import normalize_generator_helpers, normalize_header_overlays
from purego_gen.identifier_utils import (
    is_go_identifier,
    normalize_identifier_prefix,
    normalize_lib_id,
)
from purego_gen.model import TypeMappingOptions

if TYPE_CHECKING:
    from collections.abc import Mapping

_TYPE_MAPPING_DEFAULTS: dict[str, bool] = {
    "const_char_as_string": False,
    "strict_enum_typedefs": False,
    "typed_sentinel_constants": False,
}


def resolve_config_path(base_dir: Path, raw_path: str) -> Path:
    """Resolve one config-relative or absolute path.

    Returns:
        Absolute resolved path.
    """
    candidate = Path(raw_path).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (base_dir / candidate).resolve()


def _validate_package_name(value: str) -> str:
    if not is_go_identifier(value):
        message = "Go package name must match ^[A-Za-z_][A-Za-z0-9_]*$."
        raise ValueError(message)
    return value


def normalize_type_mapping(type_mapping: TypeMappingInput | None) -> TypeMappingOptions:
    """Normalize optional type-mapping input into execution-ready options.

    Returns:
        Type-mapping options with unset fields defaulted.
    """
    if type_mapping is None:
        return build_type_mapping_options(raw_values={})
    return build_type_mapping_options(raw_values=type_mapping.model_dump(exclude_none=True))


def build_type_mapping_options(
    *,
    raw_values: Mapping[str, bool],
    require_const_char_as_string: bool = False,
    context: str | None = None,
) -> TypeMappingOptions:
    """Build type-mapping options from optional boolean overrides.

    Returns:
        Type-mapping options with missing flags defaulted to `False`.

    Raises:
        RuntimeError: `const_char_as_string` is required but unresolved.
    """
    if require_const_char_as_string and "const_char_as_string" not in raw_values:
        location = "" if context is None else f"{context} "
        message = f"{location}must resolve `type_mapping.const_char_as_string`."
        raise RuntimeError(message)
    resolved_values = {**_TYPE_MAPPING_DEFAULTS, **raw_values}
    return TypeMappingOptions(
        const_char_as_string=resolved_values["const_char_as_string"],
        strict_enum_typedefs=resolved_values["strict_enum_typedefs"],
        typed_sentinel_constants=resolved_values["typed_sentinel_constants"],
    )


def _normalize_filter(filter_value: str | tuple[str, ...] | None) -> FilterSpec | None:
    if filter_value is None:
        return None
    if isinstance(filter_value, str):
        return regex_filter(filter_value)
    return exact_names_filter(filter_value)


def normalize_filters(filters: FiltersInput) -> GeneratorFilters:
    """Normalize one filter block into compiled filter specs.

    Returns:
        Per-category filter configuration ready for generator resolution.
    """
    return GeneratorFilters(
        func=_normalize_filter(filters.func),
        type_=_normalize_filter(filters.type_),
        const=_normalize_filter(filters.const),
        var=_normalize_filter(filters.var),
    )


def _normalize_headers(generator: GeneratorInput, *, base_dir: Path) -> HeaderConfig:
    if isinstance(generator.parse.headers, LocalHeadersInput):
        return LocalHeaders(
            headers=tuple(
                resolve_config_path(base_dir, raw_path)
                for raw_path in generator.parse.headers.headers
            )
        )

    header_input = generator.parse.headers
    return EnvIncludeHeaders(
        include_dir_env=header_input.include_dir_env,
        headers=header_input.headers,
    )


def build_generator_spec(
    generator: GeneratorInput,
    *,
    base_dir: Path,
    config_path: Path,
) -> GeneratorSpec:
    """Convert validated schema input into one resolved generator model.

    Returns:
        Generator config with normalized ids, emit kinds, and local paths.

    Raises:
        RuntimeError: The config contains invalid generator values.
    """
    try:
        normalized_lib_id = normalize_lib_id(generator.lib_id)
    except ValueError as error:
        message = f"config `{config_path}` generator.lib_id is invalid: {error}"
        raise RuntimeError(message) from error

    naming_input = generator.render.naming

    try:
        type_prefix = normalize_identifier_prefix(naming_input.type_prefix, allow_empty=True)
    except ValueError as error:
        message = f"config `{config_path}` generator.render.naming.type_prefix is invalid: {error}"
        raise RuntimeError(message) from error

    try:
        const_prefix = normalize_identifier_prefix(naming_input.const_prefix, allow_empty=True)
    except ValueError as error:
        message = f"config `{config_path}` generator.render.naming.const_prefix is invalid: {error}"
        raise RuntimeError(message) from error

    try:
        func_prefix = normalize_identifier_prefix(naming_input.func_prefix, allow_empty=True)
    except ValueError as error:
        message = f"config `{config_path}` generator.render.naming.func_prefix is invalid: {error}"
        raise RuntimeError(message) from error

    try:
        var_prefix = normalize_identifier_prefix(naming_input.var_prefix, allow_empty=True)
    except ValueError as error:
        message = f"config `{config_path}` generator.render.naming.var_prefix is invalid: {error}"
        raise RuntimeError(message) from error

    try:
        package_name = _validate_package_name(generator.package)
    except ValueError as error:
        message = f"config `{config_path}` generator.package is invalid: {error}"
        raise RuntimeError(message) from error

    try:
        emit_kinds = parse_emit_kinds(generator.emit, option_name="generator.emit")
    except ValueError as error:
        message = f"config `{config_path}` generator.emit is invalid: {error}"
        raise RuntimeError(message) from error

    helpers = normalize_generator_helpers(generator.render.helpers)
    if (helpers.buffer_inputs or helpers.callback_inputs) and "func" not in emit_kinds:
        message = (
            f"config `{config_path}` generator.render.helpers.buffer_inputs or "
            "generator.render.helpers.callback_inputs requires "
            "`func` in generator.emit."
        )
        raise RuntimeError(message)

    return GeneratorSpec(
        lib_id=normalized_lib_id,
        config_base_dir=base_dir,
        package=package_name,
        emit_kinds=emit_kinds,
        parse=GeneratorParseSpec(
            headers=_normalize_headers(generator, base_dir=base_dir),
            overlays=normalize_header_overlays(generator.parse.overlays),
            filters=normalize_filters(generator.parse.filters),
            exclude_filters=normalize_filters(generator.parse.exclude),
            clang_args=tuple(generator.parse.clang_args),
        ),
        render=GeneratorRenderSpec(
            naming=GeneratorNaming(
                type_prefix=type_prefix,
                const_prefix=const_prefix,
                func_prefix=func_prefix,
                var_prefix=var_prefix,
            ),
            helpers=helpers,
            type_mapping=normalize_type_mapping(generator.render.type_mapping),
            struct_accessors=bool(generator.render.struct_accessors),
        ),
    )


__all__ = [
    "build_generator_spec",
    "build_type_mapping_options",
    "normalize_filters",
    "normalize_type_mapping",
    "resolve_config_path",
]
