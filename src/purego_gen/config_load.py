# Copyright (c) 2026 purego-gen contributors.

"""Loading and resolution helpers for shared generator config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from purego_gen.config_model import (
    AppConfig,
    EnvIncludeHeaders,
    GeneratorFilters,
    GeneratorSpec,
    HeaderConfig,
    LocalHeaders,
)
from purego_gen.config_schema import (
    AppConfigInput,
    GeneratorInput,
    LocalHeadersInput,
    TypeMappingInput,
)
from purego_gen.emit_kinds import parse_emit_kinds
from purego_gen.generator_config import GeneratorConfig
from purego_gen.identifier_utils import is_go_identifier, normalize_lib_id
from purego_gen.model import TypeMappingOptions
from purego_gen.validation_error_format import format_validation_error


def read_config_text(path: Path) -> str:
    """Read one config file as UTF-8 text.

    Returns:
        File contents.

    Raises:
        RuntimeError: The file is missing or unreadable.
    """
    if not path.is_file():
        message = f"config not found: {path}"
        raise RuntimeError(message)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"failed to read config JSON at {path}: {error}"
        raise RuntimeError(message) from error


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


def load_app_config(path: Path) -> AppConfig:
    """Load and validate shared generator config.

    Returns:
        Parsed generator config.

    Raises:
        RuntimeError: File reading or schema validation fails.
    """
    resolved_path = path.expanduser().resolve()
    raw_text = read_config_text(resolved_path)
    try:
        parsed = AppConfigInput.model_validate_json(raw_text)
    except ValidationError as error:
        message = format_validation_error(error, context=f"config `{resolved_path}`")
        raise RuntimeError(message) from error

    base_dir = resolved_path.parent
    return AppConfig(
        config_path=resolved_path,
        generator=build_generator_spec(
            parsed.generator,
            base_dir=base_dir,
            config_path=resolved_path,
        ),
    )


def resolve_generator_config(generator: GeneratorSpec) -> GeneratorConfig:
    """Resolve env-backed headers into one execution-ready generator config.

    Returns:
        Generation config with concrete header paths and clang args.

    Raises:
        RuntimeError: Header resolution or environment lookup fails.
    """
    if isinstance(generator.headers, LocalHeaders):
        local_header_paths = generator.headers.headers
        for header_path in local_header_paths:
            if not header_path.is_file():
                message = f"header not found: {header_path}"
                raise RuntimeError(message)
        return GeneratorConfig(
            lib_id=generator.lib_id,
            headers=tuple(str(path) for path in local_header_paths),
            package=generator.package,
            emit_kinds=generator.emit_kinds,
            func_filter=generator.filters.func,
            type_filter=generator.filters.type_,
            const_filter=generator.filters.const,
            var_filter=generator.filters.var,
            clang_args=generator.clang_args,
            type_mapping=generator.type_mapping,
        )

    env_headers = generator.headers
    include_dir_value = os.environ.get(env_headers.include_dir_env, "").strip()
    if not include_dir_value:
        message = (
            f"required env {env_headers.include_dir_env} is not set for headers.kind=`env_include`."
        )
        raise RuntimeError(message)

    include_dir = Path(include_dir_value).expanduser().resolve()
    if not include_dir.is_dir():
        message = (
            f"include directory from env {env_headers.include_dir_env} "
            f"does not exist: {include_dir}"
        )
        raise RuntimeError(message)

    resolved_header_paths: list[str] = []
    for header_name in env_headers.headers:
        header_path = (include_dir / header_name).resolve()
        if not header_path.is_file():
            message = (
                f"header not found from env include directory "
                f"{env_headers.include_dir_env}: {header_path}"
            )
            raise RuntimeError(message)
        resolved_header_paths.append(str(header_path))

    return GeneratorConfig(
        lib_id=generator.lib_id,
        headers=tuple(resolved_header_paths),
        package=generator.package,
        emit_kinds=generator.emit_kinds,
        func_filter=generator.filters.func,
        type_filter=generator.filters.type_,
        const_filter=generator.filters.const,
        var_filter=generator.filters.var,
        clang_args=("-I", str(include_dir), *generator.clang_args),
        type_mapping=generator.type_mapping,
    )


def dump_signature_payload(path: Path) -> dict[str, object]:
    """Load one config file as a generic JSON object for signature tests.

    Returns:
        Decoded JSON object.

    Raises:
        RuntimeError: The file cannot be read or parsed as JSON.
        TypeError: The decoded JSON payload is not an object.
    """
    raw_text = read_config_text(path.expanduser().resolve())
    try:
        raw_value = cast("object", json.loads(raw_text))
    except json.JSONDecodeError as error:
        message = (
            f"failed to parse config JSON at {path}: "
            f"{error.msg} (line {error.lineno}, column {error.colno})"
        )
        raise RuntimeError(message) from error
    if not isinstance(raw_value, dict):
        message = f"config `{path}` must decode to a JSON object"
        raise TypeError(message)
    return cast("dict[str, object]", raw_value)


__all__ = [
    "build_generator_spec",
    "dump_signature_payload",
    "load_app_config",
    "read_config_text",
    "resolve_config_path",
    "resolve_generator_config",
]
