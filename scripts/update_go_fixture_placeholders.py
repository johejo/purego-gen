# Copyright (c) 2026 purego-gen contributors.

"""Update/check Go fixture placeholder files by invoking purego-gen CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from purego_gen.cli_invocation import (
    PuregoGenInvocation,
    build_purego_gen_command,
    build_src_pythonpath_env,
)
from purego_gen.model import TypeMappingOptions
from purego_gen.pkg_config import run_pkg_config_stdout, run_pkg_config_tokens
from purego_gen.process_exec import run_command
from purego_gen.target_profile import load_target_profile_catalog

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_SMOKE_HEADER_PATH = _FIXTURES_DIR / "smoke_runtime.h"
_SMOKE_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_module" / "generated.go"
_SMOKE_STRING_HEADER_PATH = _FIXTURES_DIR / "smoke_string_runtime.h"
_SMOKE_STRING_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_string_module" / "generated.go"
_TARGET_PROFILE_CATALOG_PATH = _FIXTURES_DIR / "target_profiles" / "libzstd_profiles.json"
_LIBZSTD_PROFILE_ID = "libzstd_v1"
_LIBZSTD_STRICT_PROFILE_ID = "libzstd_strict"
_ZSTD_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_zstd_module" / "generated.go"
_ZSTD_STRICT_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_zstd_strict_module" / "generated.go"


class _ParsedArgs(argparse.Namespace):
    """Typed argparse namespace for this script."""

    check: bool


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


def _run_purego_gen(invocation: PuregoGenInvocation) -> str:
    """Run purego-gen CLI and return generated source.

    Returns:
        Generated Go source.

    Raises:
        RuntimeError: CLI execution fails.
    """
    command = build_purego_gen_command(invocation, python_executable=sys.executable)
    result = run_command(
        command,
        cwd=_REPO_ROOT,
        env=build_src_pythonpath_env(src_dir=_SRC_DIR),
    )
    if result.returncode != 0:
        message = (
            "failed to generate Go fixture placeholder via purego-gen.\n"
            f"command: {' '.join(command)}\n"
            f"stderr:\n{result.stderr}"
        )
        raise RuntimeError(message)
    return result.stdout


def _resolve_libzstd_include_dir_and_cflags() -> tuple[Path, tuple[str, ...]]:
    """Resolve libzstd include directory and pkg-config cflags.

    Returns:
        Include directory and clang flags.

    Raises:
        RuntimeError: Include-directory resolution fails.
    """
    cflags = run_pkg_config_tokens("libzstd", "--cflags")
    include_dir = Path(run_pkg_config_stdout("libzstd", "--variable=includedir")).expanduser()
    if not include_dir.is_dir():
        message = f"failed to locate libzstd include directory from pkg-config: {include_dir}"
        raise RuntimeError(message)
    return include_dir, cflags


def _resolve_header_paths(include_dir: Path, header_names: tuple[str, ...]) -> tuple[Path, ...]:
    """Resolve required header names from include directory.

    Returns:
        Resolved header paths in profile-defined order.

    Raises:
        RuntimeError: One or more headers cannot be found.
    """
    resolved: list[Path] = []
    for header_name in header_names:
        header_path = (include_dir / header_name).resolve()
        if not header_path.is_file():
            message = f"failed to locate {header_name} from pkg-config includedir: {header_path}"
            raise RuntimeError(message)
        resolved.append(header_path)
    return tuple(resolved)


def _generated_fixture_sources() -> dict[Path, str]:
    """Generate all fixture placeholder sources from CLI.

    Returns:
        Mapping of output path to generated source.
    """
    smoke_source = _run_purego_gen(
        PuregoGenInvocation(
            lib_id="fixture_lib",
            header_paths=(_SMOKE_HEADER_PATH.resolve(),),
            package_name="fixture",
            emit_kinds="func,var",
        )
    )
    smoke_string_source = _run_purego_gen(
        PuregoGenInvocation(
            lib_id="fixture_lib",
            header_paths=(_SMOKE_STRING_HEADER_PATH.resolve(),),
            package_name="fixture",
            emit_kinds="func",
            type_mapping=TypeMappingOptions(const_char_as_string=True),
        )
    )

    include_dir, zstd_cflags = _resolve_libzstd_include_dir_and_cflags()
    zstd_profile = load_target_profile_catalog(_TARGET_PROFILE_CATALOG_PATH, _LIBZSTD_PROFILE_ID)
    zstd_header_paths = _resolve_header_paths(include_dir, zstd_profile.header_names)
    zstd_source = _run_purego_gen(
        PuregoGenInvocation(
            lib_id="zstd",
            header_paths=zstd_header_paths,
            package_name="zstdfixture",
            emit_kinds=zstd_profile.emit_kinds,
            clang_args=zstd_cflags,
            func_filter=zstd_profile.function_filter,
            type_filter=zstd_profile.type_filter,
            const_filter=zstd_profile.const_filter,
            type_mapping=zstd_profile.type_mapping,
        )
    )

    zstd_strict_profile = load_target_profile_catalog(
        _TARGET_PROFILE_CATALOG_PATH,
        _LIBZSTD_STRICT_PROFILE_ID,
    )
    zstd_strict_header_paths = _resolve_header_paths(include_dir, zstd_strict_profile.header_names)
    zstd_strict_source = _run_purego_gen(
        PuregoGenInvocation(
            lib_id="zstd",
            header_paths=zstd_strict_header_paths,
            package_name="zstdfixturestrict",
            emit_kinds=zstd_strict_profile.emit_kinds,
            clang_args=zstd_cflags,
            func_filter=zstd_strict_profile.function_filter,
            type_filter=zstd_strict_profile.type_filter,
            const_filter=zstd_strict_profile.const_filter,
            type_mapping=zstd_strict_profile.type_mapping,
        )
    )
    return {
        _SMOKE_OUTPUT_PATH: smoke_source,
        _SMOKE_STRING_OUTPUT_PATH: smoke_string_source,
        _ZSTD_OUTPUT_PATH: zstd_source,
        _ZSTD_STRICT_OUTPUT_PATH: zstd_strict_source,
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
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
    _write_line("run: scripts/uv-run-python-src.sh scripts/update_go_fixture_placeholders.py")
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
