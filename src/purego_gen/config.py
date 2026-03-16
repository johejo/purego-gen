# Copyright (c) 2026 purego-gen contributors.

"""Shared JSON config schema and resolution helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, cast

from annotated_types import Len
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, ValidationError

from purego_gen.emit_kinds import parse_emit_kinds
from purego_gen.generator_config import GeneratorConfig
from purego_gen.identifier_utils import is_go_identifier, normalize_lib_id
from purego_gen.model import TypeMappingOptions
from purego_gen.validation_error_format import format_validation_error

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
NonEmptyStrTuple = Annotated[tuple[NonEmptyStr, ...], Len(min_length=1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TypeMappingInput(_StrictModel):
    """Optional type-mapping overrides."""

    const_char_as_string: StrictBool | None = None
    strict_enum_typedefs: StrictBool | None = None
    typed_sentinel_constants: StrictBool | None = None


class FiltersInput(_StrictModel):
    """Optional declaration filters."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    func: NonEmptyStr | None = None
    type_: NonEmptyStr | None = Field(default=None, alias="type")
    const: NonEmptyStr | None = None
    var: NonEmptyStr | None = None


class LocalHeadersInput(_StrictModel):
    """Header configuration for local file paths."""

    kind: Literal["local"]
    headers: NonEmptyStrTuple


class EnvIncludeHeadersInput(_StrictModel):
    """Header configuration resolved from an include-directory environment variable."""

    kind: Literal["env_include"]
    include_dir_env: NonEmptyStr
    headers: NonEmptyStrTuple


HeaderInput = Annotated[LocalHeadersInput | EnvIncludeHeadersInput, Field(discriminator="kind")]


class CompileCRuntimeInput(_StrictModel):
    """Runtime library definition by compiling local C sources."""

    kind: Literal["compile_c"]
    sources: NonEmptyStrTuple
    cflags: NonEmptyStrTuple | None = None
    ldflags: NonEmptyStrTuple | None = None


class EnvLibdirRuntimeInput(_StrictModel):
    """Runtime library definition from a library-directory environment variable."""

    kind: Literal["env_libdir"]
    lib_dir_env: NonEmptyStr
    library_names: NonEmptyStrTuple


RuntimeInput = Annotated[
    CompileCRuntimeInput | EnvLibdirRuntimeInput,
    Field(discriminator="kind"),
]


class GeneratorInput(_StrictModel):
    """Generator configuration loaded from JSON."""

    lib_id: NonEmptyStr
    package: NonEmptyStr
    emit: NonEmptyStr
    headers: HeaderInput
    filters: FiltersInput = Field(default_factory=FiltersInput)
    type_mapping: TypeMappingInput = Field(default_factory=TypeMappingInput)
    clang_args: tuple[NonEmptyStr, ...] = ()


class GoldenInput(_StrictModel):
    """Harness-only configuration."""

    runtime: RuntimeInput | None = None


class AppConfigInput(_StrictModel):
    """Top-level shared config file."""

    schema_version: Literal[1]
    generator: GeneratorInput
    golden: GoldenInput | None = None


@dataclass(frozen=True, slots=True)
class GeneratorFilters:
    """Optional per-category declaration filters."""

    func: str | None = None
    type_: str | None = None
    const: str | None = None
    var: str | None = None


@dataclass(frozen=True, slots=True)
class LocalHeaders:
    """Header source definition for local file paths."""

    headers: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class EnvIncludeHeaders:
    """Header source definition via include-directory environment variable."""

    include_dir_env: str
    headers: tuple[str, ...]


HeaderConfig = LocalHeaders | EnvIncludeHeaders


@dataclass(frozen=True, slots=True)
class CompileCRuntime:
    """Runtime library definition by compiling local C sources."""

    sources: tuple[Path, ...]
    cflags: tuple[str, ...]
    ldflags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnvLibdirRuntime:
    """Runtime library definition via library-directory environment variable."""

    lib_dir_env: str
    library_names: tuple[str, ...]


RuntimeConfig = CompileCRuntime | EnvLibdirRuntime


@dataclass(frozen=True, slots=True)
class GoldenConfig:
    """Harness-only config block."""

    runtime: RuntimeConfig | None = None


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    """Resolved generator configuration prior to env-backed header expansion."""

    lib_id: str
    package: str
    emit_kinds: tuple[str, ...]
    headers: HeaderConfig
    filters: GeneratorFilters
    type_mapping: TypeMappingOptions
    clang_args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Shared JSON config loaded from disk."""

    config_path: Path
    generator: GeneratorSpec
    golden: GoldenConfig | None = None


def _read_config_text(path: Path) -> str:
    if not path.is_file():
        message = f"config not found: {path}"
        raise RuntimeError(message)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"failed to read config JSON at {path}: {error}"
        raise RuntimeError(message) from error


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


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (base_dir / candidate).resolve()


def _to_generator_spec(
    generator: GeneratorInput,
    *,
    base_dir: Path,
    config_path: Path,
) -> GeneratorSpec:
    if isinstance(generator.headers, LocalHeadersInput):
        headers: HeaderConfig = LocalHeaders(
            headers=tuple(
                _resolve_path(base_dir, raw_path) for raw_path in generator.headers.headers
            )
        )
    else:
        headers = EnvIncludeHeaders(
            include_dir_env=generator.headers.include_dir_env,
            headers=generator.headers.headers,
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


def _normalize_optional_tuple(value: tuple[str, ...] | None) -> tuple[str, ...]:
    return value if value is not None else ()


def _to_golden_config(golden: GoldenInput | None, *, base_dir: Path) -> GoldenConfig | None:
    if golden is None:
        return None

    runtime: RuntimeConfig | None
    if golden.runtime is None:
        runtime = None
    elif isinstance(golden.runtime, CompileCRuntimeInput):
        runtime = CompileCRuntime(
            sources=tuple(_resolve_path(base_dir, raw_path) for raw_path in golden.runtime.sources),
            cflags=_normalize_optional_tuple(golden.runtime.cflags),
            ldflags=_normalize_optional_tuple(golden.runtime.ldflags),
        )
    else:
        runtime = EnvLibdirRuntime(
            lib_dir_env=golden.runtime.lib_dir_env,
            library_names=golden.runtime.library_names,
        )
    return GoldenConfig(runtime=runtime)


def load_app_config(path: Path) -> AppConfig:
    """Load and validate a shared config file.

    Returns:
        Parsed config payload.

    Raises:
        RuntimeError: File reading or schema validation fails.
    """
    resolved_path = path.expanduser().resolve()
    raw_text = _read_config_text(resolved_path)
    try:
        parsed = AppConfigInput.model_validate_json(raw_text)
    except ValidationError as error:
        message = format_validation_error(error, context=f"config `{resolved_path}`")
        raise RuntimeError(message) from error

    base_dir = resolved_path.parent
    return AppConfig(
        config_path=resolved_path,
        generator=_to_generator_spec(
            parsed.generator,
            base_dir=base_dir,
            config_path=resolved_path,
        ),
        golden=_to_golden_config(parsed.golden, base_dir=base_dir),
    )


def resolve_generator_config(generator: GeneratorSpec) -> GeneratorConfig:
    """Resolve env-backed headers into one execution-ready generator config.

    Returns:
        Generation config with concrete header paths and clang args.

    Raises:
        RuntimeError: Header resolution or environment lookup fails.
    """
    if isinstance(generator.headers, LocalHeaders):
        local_headers = generator.headers
        local_header_paths = local_headers.headers
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
    raw_text = _read_config_text(path.expanduser().resolve())
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
    "AppConfig",
    "AppConfigInput",
    "CompileCRuntime",
    "CompileCRuntimeInput",
    "EnvIncludeHeaders",
    "EnvIncludeHeadersInput",
    "EnvLibdirRuntime",
    "EnvLibdirRuntimeInput",
    "FiltersInput",
    "GeneratorConfig",
    "GeneratorFilters",
    "GeneratorInput",
    "GeneratorSpec",
    "GoldenConfig",
    "GoldenInput",
    "HeaderConfig",
    "HeaderInput",
    "LocalHeaders",
    "LocalHeadersInput",
    "NonEmptyStr",
    "NonEmptyStrTuple",
    "RuntimeConfig",
    "RuntimeInput",
    "TypeMappingInput",
    "dump_signature_payload",
    "load_app_config",
    "resolve_generator_config",
]
