# Copyright (c) 2026 purego-gen contributors.

"""Loading and resolution helpers for shared generator config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from purego_gen.config_model import AppConfig, GeneratorSpec, LocalHeaders
from purego_gen.config_normalize import build_generator_spec
from purego_gen.config_schema import AppConfigInput
from purego_gen.generator_config import GeneratorConfig
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
        return _build_generator_config(
            generator,
            headers=tuple(str(path) for path in local_header_paths),
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

    return _build_generator_config(
        generator,
        headers=tuple(resolved_header_paths),
        clang_args=("-I", str(include_dir), *generator.clang_args),
    )


def _build_generator_config(
    generator: GeneratorSpec,
    *,
    headers: tuple[str, ...],
    clang_args: tuple[str, ...] | None = None,
) -> GeneratorConfig:
    """Build execution-ready config once header resolution is complete.

    Returns:
        Normalized generator config with resolved headers and clang args.
    """
    resolved_clang_args = generator.clang_args if clang_args is None else clang_args
    return GeneratorConfig(
        lib_id=generator.lib_id,
        headers=headers,
        package=generator.package,
        emit_kinds=generator.emit_kinds,
        func_filter=generator.filters.func,
        type_filter=generator.filters.type_,
        const_filter=generator.filters.const,
        var_filter=generator.filters.var,
        func_exclude_filter=generator.exclude_filters.func,
        type_exclude_filter=generator.exclude_filters.type_,
        const_exclude_filter=generator.exclude_filters.const,
        var_exclude_filter=generator.exclude_filters.var,
        clang_args=resolved_clang_args,
        helpers=generator.helpers,
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
    "dump_signature_payload",
    "load_app_config",
    "read_config_text",
    "resolve_generator_config",
]
