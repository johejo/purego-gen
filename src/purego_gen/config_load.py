# Copyright (c) 2026 purego-gen contributors.

"""Loading and resolution helpers for shared generator config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import BaseModel

from purego_gen.config_model import AppConfig, GeneratorSpec, HeaderOverlay, LocalHeaders
from purego_gen.config_normalize import build_generator_spec, resolve_config_path
from purego_gen.config_schema import AppConfigInput
from purego_gen.generator_config import GeneratorConfig, build_generator_config
from purego_gen.json_load import load_json_model, read_json_text

if TYPE_CHECKING:
    from purego_gen.config_schema import GeneratorInput


class _HasGeneratorInput(Protocol):
    """Protocol for config payloads that include one generator block."""

    generator: GeneratorInput


def load_generator_config_input[ModelT: BaseModel](
    path: Path,
    *,
    model_type: type[ModelT],
) -> tuple[Path, ModelT, GeneratorSpec]:
    """Load one config model and normalize its generator block.

    Returns:
        Resolved config path, parsed top-level model, and normalized generator spec.
    """
    resolved_path = path.expanduser().resolve()
    parsed = load_json_model(
        resolved_path,
        model_type=model_type,
        context=f"config `{resolved_path}`",
    )
    generator_input = cast("_HasGeneratorInput", parsed).generator
    generator = build_generator_spec(
        generator_input,
        base_dir=resolved_path.parent,
        config_path=resolved_path,
    )
    return resolved_path, parsed, generator


def load_app_config(path: Path) -> AppConfig:
    """Load and validate shared generator config.

    Returns:
        Parsed generator config.
    """
    resolved_path, _, generator = load_generator_config_input(
        path,
        model_type=AppConfigInput,
    )
    return AppConfig(
        config_path=resolved_path,
        generator=generator,
    )


def resolve_generator_config(generator: GeneratorSpec) -> GeneratorConfig:
    """Resolve env-backed headers into one execution-ready generator config.

    Returns:
        Generation config with concrete header paths and clang args.

    Raises:
        RuntimeError: Header resolution or environment lookup fails.
    """

    def _resolve_overlay_paths(*, base_dir: Path) -> tuple[HeaderOverlay, ...]:
        return tuple(
            HeaderOverlay(
                path=str(resolve_config_path(base_dir, overlay.path)),
                content=overlay.content,
            )
            for overlay in generator.overlays
        )

    if isinstance(generator.headers, LocalHeaders):
        local_header_paths = generator.headers.headers
        resolved_overlays = _resolve_overlay_paths(base_dir=generator.config_base_dir)
        overlay_paths = {overlay.path for overlay in resolved_overlays}
        for header_path in local_header_paths:
            if not header_path.is_file() and str(header_path) not in overlay_paths:
                message = f"header not found: {header_path}"
                raise RuntimeError(message)
        return build_generator_config(
            generator,
            headers=tuple(str(path) for path in local_header_paths),
            overlays=resolved_overlays,
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
    resolved_overlays = _resolve_overlay_paths(base_dir=include_dir)
    overlay_paths = {overlay.path for overlay in resolved_overlays}
    for header_name in env_headers.headers:
        header_path = (include_dir / header_name).resolve()
        if not header_path.is_file() and str(header_path) not in overlay_paths:
            message = (
                f"header not found from env include directory "
                f"{env_headers.include_dir_env}: {header_path}"
            )
            raise RuntimeError(message)
        resolved_header_paths.append(str(header_path))

    return build_generator_config(
        generator,
        headers=tuple(resolved_header_paths),
        clang_args=("-I", str(include_dir), *generator.clang_args),
        overlays=resolved_overlays,
    )


def dump_signature_payload(path: Path) -> dict[str, object]:
    """Load one config file as a generic JSON object for signature tests.

    Returns:
        Decoded JSON object.

    Raises:
        RuntimeError: The file cannot be read or parsed as JSON.
        TypeError: The decoded JSON payload is not an object.
    """
    raw_text = read_json_text(path.expanduser().resolve())
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
    "load_generator_config_input",
    "resolve_generator_config",
]
