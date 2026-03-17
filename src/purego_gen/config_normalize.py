# Copyright (c) 2026 purego-gen contributors.

"""Pure normalization helpers for shared generator config."""

from __future__ import annotations

from pathlib import Path

from purego_gen.config_model import (
    EnvIncludeHeaders,
    GeneratorFilters,
    GeneratorSpec,
    HeaderConfig,
    LocalHeaders,
)
from purego_gen.config_schema import GeneratorInput, LocalHeadersInput, TypeMappingInput
from purego_gen.emit_kinds import parse_emit_kinds
from purego_gen.identifier_utils import is_go_identifier, normalize_lib_id
from purego_gen.model import TypeMappingOptions


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


def _normalize_type_mapping(type_mapping: TypeMappingInput) -> TypeMappingOptions:
    return TypeMappingOptions(
        const_char_as_string=bool(type_mapping.const_char_as_string),
        strict_enum_typedefs=bool(type_mapping.strict_enum_typedefs),
        typed_sentinel_constants=bool(type_mapping.typed_sentinel_constants),
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
    if isinstance(generator.headers, LocalHeadersInput):
        headers: HeaderConfig = LocalHeaders(
            headers=tuple(
                resolve_config_path(base_dir, raw_path) for raw_path in generator.headers.headers
            )
        )
    else:
        header_input = generator.headers
        headers = EnvIncludeHeaders(
            include_dir_env=header_input.include_dir_env,
            headers=header_input.headers,
        )

    try:
        normalized_lib_id = normalize_lib_id(generator.lib_id)
    except ValueError as error:
        message = f"config `{config_path}` generator.lib_id is invalid: {error}"
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

    return GeneratorSpec(
        lib_id=normalized_lib_id,
        package=package_name,
        emit_kinds=emit_kinds,
        headers=headers,
        filters=GeneratorFilters(
            func=generator.filters.func,
            type_=generator.filters.type_,
            const=generator.filters.const,
            var=generator.filters.var,
        ),
        type_mapping=_normalize_type_mapping(generator.type_mapping),
        clang_args=tuple(generator.clang_args),
    )


__all__ = [
    "build_generator_spec",
    "resolve_config_path",
]
