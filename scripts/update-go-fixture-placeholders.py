# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: INP001

"""Update/check Go fixture placeholder files by invoking purego-gen CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from purego_gen.model import TypeMappingOptions
from purego_gen.pkg_config import run_pkg_config_stdout, run_pkg_config_tokens

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_SMOKE_HEADER_PATH = _FIXTURES_DIR / "smoke_runtime.h"
_SMOKE_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_module" / "generated.go"
_SMOKE_STRING_HEADER_PATH = _FIXTURES_DIR / "smoke_string_runtime.h"
_SMOKE_STRING_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_string_module" / "generated.go"
_ZSTD_PROFILE_PATH = _FIXTURES_DIR / "target_profiles" / "libzstd_v1.json"
_ZSTD_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_zstd_module" / "generated.go"


class _ParsedArgs(argparse.Namespace):
    """Typed argparse namespace for this script."""

    check: bool


@dataclass(frozen=True, slots=True)
class _PuregoGenInvocation:
    """One purego-gen CLI invocation configuration."""

    lib_id: str
    header_path: Path
    package_name: str
    emit_kinds: str
    clang_args: tuple[str, ...] = ()
    func_filter: str | None = None
    type_filter: str | None = None
    type_mapping: TypeMappingOptions = field(default_factory=TypeMappingOptions)


@dataclass(frozen=True, slots=True)
class _LibzstdProfile:
    """Stable profile used for libzstd fixture generation."""

    emit_kinds: str
    required_functions: tuple[str, ...]
    required_types: tuple[str, ...]
    function_filter: str
    type_filter: str
    type_mapping: TypeMappingOptions


def _write_line(message: str) -> None:
    """Write one line to stdout."""
    sys.stdout.write(f"{message}\n")


def _parse_args() -> _ParsedArgs:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Update/check committed generated.go files for Go runtime fixtures.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write files; fail when committed files are out of date.",
    )
    return cast("_ParsedArgs", parser.parse_args())


def _run_purego_gen(invocation: _PuregoGenInvocation) -> str:
    """Run purego-gen CLI and return generated source.

    Returns:
        Generated Go source.

    Raises:
        RuntimeError: CLI execution fails.
    """
    command = [
        sys.executable,
        "-m",
        "purego_gen",
        "--lib-id",
        invocation.lib_id,
        "--header",
        str(invocation.header_path),
        "--pkg",
        invocation.package_name,
        "--emit",
        invocation.emit_kinds,
    ]
    if invocation.func_filter is not None:
        command.extend(["--func-filter", invocation.func_filter])
    if invocation.type_filter is not None:
        command.extend(["--type-filter", invocation.type_filter])
    if invocation.type_mapping.const_char_as_string:
        command.append("--const-char-as-string")
    if invocation.type_mapping.strict_opaque_handles:
        command.append("--strict-opaque-handles")
    if invocation.clang_args:
        command.extend(["--", *invocation.clang_args])

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(_SRC_DIR)
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}:{existing_pythonpath}"
    )
    result = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )
    if result.returncode != 0:
        message = (
            "failed to generate Go fixture placeholder via purego-gen.\n"
            f"command: {' '.join(command)}\n"
            f"stderr:\n{result.stderr}"
        )
        raise RuntimeError(message)
    return result.stdout


def _build_exact_symbol_regex(symbols: tuple[str, ...]) -> str:
    """Build exact-match regex from symbol names.

    Returns:
        Regex pattern matching the provided symbols.
    """
    escaped = [re.escape(symbol) for symbol in symbols]
    return "^(" + "|".join(escaped) + ")$"


def _read_required_non_empty_string(raw: dict[str, object], key: str) -> str:
    """Read one required non-empty string field from profile JSON object.

    Returns:
        String value for `key`.

    Raises:
        RuntimeError: The field is missing or empty.
    """
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        message = f"libzstd profile must define non-empty string `{key}`."
        raise RuntimeError(message)
    return value


def _read_required_non_empty_string_array(raw: dict[str, object], key: str) -> tuple[str, ...]:
    """Read one required non-empty string array field from profile JSON object.

    Returns:
        Tuple of string values for `key`.

    Raises:
        RuntimeError: The field is missing, empty, or includes non-string/empty items.
    """
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        message = f"libzstd profile must define non-empty array `{key}`."
        raise RuntimeError(message)

    items: list[str] = []
    for element in cast("list[object]", value):
        if not isinstance(element, str) or not element:
            message = f"libzstd profile `{key}` must contain non-empty strings."
            raise RuntimeError(message)
        items.append(element)
    return tuple(items)


def _read_required_bool(raw: dict[str, object], key: str) -> bool:
    """Read one required bool field from profile JSON object.

    Returns:
        Bool value for `key`.

    Raises:
        TypeError: The field is missing or not a bool.
    """
    value = raw.get(key)
    if not isinstance(value, bool):
        message = f"libzstd profile must define bool `{key}`."
        raise TypeError(message)
    return value


def _read_type_mapping_options(raw: dict[str, object]) -> TypeMappingOptions:
    """Read type-mapping options from profile JSON object.

    Returns:
        Parsed type-mapping option set.

    Raises:
        TypeError: Type-mapping profile section is malformed.
    """
    raw_type_mapping = raw.get("type_mapping")
    if not isinstance(raw_type_mapping, dict):
        message = "libzstd profile `type_mapping` must be a JSON object."
        raise TypeError(message)
    type_mapping_dict = cast("dict[str, object]", raw_type_mapping)
    return TypeMappingOptions(
        const_char_as_string=_read_required_bool(type_mapping_dict, "const_char_as_string"),
        strict_opaque_handles=_read_required_bool(type_mapping_dict, "strict_opaque_handles"),
    )


def _load_libzstd_profile() -> _LibzstdProfile:
    """Load stable libzstd profile from JSON.

    Returns:
        Parsed profile model.

    Raises:
        RuntimeError: Profile is missing or malformed.
        TypeError: Profile JSON root is not an object.
    """
    if not _ZSTD_PROFILE_PATH.is_file():
        message = f"libzstd profile not found: {_ZSTD_PROFILE_PATH}"
        raise RuntimeError(message)
    raw_object = cast("object", json.loads(_ZSTD_PROFILE_PATH.read_text(encoding="utf-8")))
    if not isinstance(raw_object, dict):
        message = "libzstd profile root must be a JSON object."
        raise TypeError(message)
    raw = cast("dict[str, object]", raw_object)
    emit_kinds = _read_required_non_empty_string(raw, "emit_kinds")
    required_function_tuple = _read_required_non_empty_string_array(raw, "required_functions")
    required_type_tuple = _read_required_non_empty_string_array(raw, "required_types")
    type_mapping = _read_type_mapping_options(raw)
    return _LibzstdProfile(
        emit_kinds=emit_kinds,
        required_functions=required_function_tuple,
        required_types=required_type_tuple,
        function_filter=_build_exact_symbol_regex(required_function_tuple),
        type_filter=_build_exact_symbol_regex(required_type_tuple),
        type_mapping=type_mapping,
    )


def _resolve_libzstd_header_and_cflags() -> tuple[Path, tuple[str, ...]]:
    """Resolve libzstd header path and pkg-config cflags.

    Returns:
        Header path and clang flags.

    Raises:
        RuntimeError: Header resolution fails.
    """
    cflags = run_pkg_config_tokens("libzstd", "--cflags")
    include_dir = Path(run_pkg_config_stdout("libzstd", "--variable=includedir")).expanduser()
    header_path = (include_dir / "zstd.h").resolve()
    if not header_path.is_file():
        message = f"failed to locate zstd.h from pkg-config includedir: {header_path}"
        raise RuntimeError(message)
    return header_path, cflags


def _generated_fixture_sources() -> dict[Path, str]:
    """Generate all fixture placeholder sources from CLI.

    Returns:
        Mapping of output path to generated source.
    """
    smoke_source = _run_purego_gen(
        _PuregoGenInvocation(
            lib_id="fixture_lib",
            header_path=_SMOKE_HEADER_PATH.resolve(),
            package_name="fixture",
            emit_kinds="func,var",
        )
    )
    smoke_string_source = _run_purego_gen(
        _PuregoGenInvocation(
            lib_id="fixture_lib",
            header_path=_SMOKE_STRING_HEADER_PATH.resolve(),
            package_name="fixture",
            emit_kinds="func",
            type_mapping=TypeMappingOptions(const_char_as_string=True),
        )
    )

    zstd_header, zstd_cflags = _resolve_libzstd_header_and_cflags()
    zstd_profile = _load_libzstd_profile()
    zstd_source = _run_purego_gen(
        _PuregoGenInvocation(
            lib_id="zstd",
            header_path=zstd_header,
            package_name="zstdfixture",
            emit_kinds=zstd_profile.emit_kinds,
            clang_args=zstd_cflags,
            func_filter=zstd_profile.function_filter,
            type_filter=zstd_profile.type_filter,
            type_mapping=zstd_profile.type_mapping,
        )
    )
    return {
        _SMOKE_OUTPUT_PATH: smoke_source,
        _SMOKE_STRING_OUTPUT_PATH: smoke_string_source,
        _ZSTD_OUTPUT_PATH: zstd_source,
    }


def _check_or_write_generated_sources(*, check: bool) -> int:
    """Check or write generated fixture placeholders.

    Returns:
        Process exit code (`0` for success, `1` for mismatch in check mode).
    """
    generated = _generated_fixture_sources()
    stale_paths: list[Path] = []

    for output_path, source in generated.items():
        if check:
            if not output_path.is_file() or output_path.read_text(encoding="utf-8") != source:
                stale_paths.append(output_path)
            continue
        output_path.write_text(source, encoding="utf-8")
        _write_line(f"updated: {output_path}")

    if not check:
        return 0
    if not stale_paths:
        _write_line("go fixture placeholders are up to date.")
        return 0

    _write_line("go fixture placeholders are stale:")
    for path in stale_paths:
        _write_line(f"- {path}")
    _write_line("run: scripts/uv-run-python-src.sh scripts/update-go-fixture-placeholders.py")
    return 1


def main() -> int:
    """Run script entrypoint.

    Returns:
        Exit status code.
    """
    args = _parse_args()
    try:
        return _check_or_write_generated_sources(check=args.check)
    except (RuntimeError, TypeError) as error:
        sys.stderr.write(f"{error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
