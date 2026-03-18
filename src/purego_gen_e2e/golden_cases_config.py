# Copyright (c) 2026 purego-gen contributors.

"""Golden-case config schema, models, and loaders."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from purego_gen.config_load import load_generator_config_input
from purego_gen.config_model import GeneratorSpec
from purego_gen.config_normalize import resolve_config_path
from purego_gen.config_schema import GeneratorInput
from purego_gen.config_shared import NonEmptyStr, NonEmptyStrTuple, StrictModel

PathType = Path
GeneratorSpecType = GeneratorSpec
GeneratorInputType = GeneratorInput
NonEmptyStrType = NonEmptyStr
NonEmptyStrTupleType = NonEmptyStrTuple


class CompileCRuntimeInput(StrictModel):
    """Runtime library definition by compiling local C sources."""

    kind: Literal["compile_c"]
    sources: NonEmptyStrTupleType
    cflags: NonEmptyStrTupleType | None = None
    ldflags: NonEmptyStrTupleType | None = None


class EnvLibdirRuntimeInput(StrictModel):
    """Runtime library definition from a library-directory environment variable."""

    kind: Literal["env_libdir"]
    lib_dir_env: NonEmptyStrType
    library_names: NonEmptyStrTupleType


RuntimeInput = Annotated[
    CompileCRuntimeInput | EnvLibdirRuntimeInput,
    Field(discriminator="kind"),
]


class GoldenInput(StrictModel):
    """Harness-only configuration."""

    runtime: RuntimeInput | None = None


class AppConfigInput(StrictModel):
    """Top-level golden-case config file."""

    schema_version: Literal[1]
    generator: GeneratorInputType
    golden: GoldenInput | None = None


@dataclass(frozen=True, slots=True)
class CompileCRuntime:
    """Runtime library definition by compiling local C sources."""

    sources: tuple[PathType, ...]
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
    """Harness-only resolved config block."""

    runtime: RuntimeConfig | None = None


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Golden-case config loaded from disk."""

    config_path: PathType
    generator: GeneratorSpecType
    golden: GoldenConfig | None = None


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
            sources=tuple(
                resolve_config_path(base_dir, raw_path) for raw_path in golden.runtime.sources
            ),
            cflags=_normalize_optional_tuple(golden.runtime.cflags),
            ldflags=_normalize_optional_tuple(golden.runtime.ldflags),
        )
    else:
        runtime = EnvLibdirRuntime(
            lib_dir_env=golden.runtime.lib_dir_env,
            library_names=golden.runtime.library_names,
        )
    return GoldenConfig(runtime=runtime)


def load_case_config(path: Path) -> AppConfig:
    """Load and validate one golden-case config file.

    Returns:
        Parsed golden-case config.
    """
    resolved_path, parsed, generator = load_generator_config_input(
        path,
        model_type=AppConfigInput,
    )
    return AppConfig(
        config_path=resolved_path,
        generator=generator,
        golden=_to_golden_config(parsed.golden, base_dir=resolved_path.parent),
    )


__all__ = [
    "AppConfig",
    "AppConfigInput",
    "CompileCRuntime",
    "CompileCRuntimeInput",
    "EnvLibdirRuntime",
    "EnvLibdirRuntimeInput",
    "GoldenConfig",
    "GoldenInput",
    "RuntimeConfig",
    "RuntimeInput",
    "load_case_config",
]
