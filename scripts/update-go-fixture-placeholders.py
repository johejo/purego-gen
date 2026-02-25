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
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from purego_gen.pkg_config import run_pkg_config_stdout, run_pkg_config_tokens

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
_SMOKE_HEADER_PATH = _FIXTURES_DIR / "smoke_runtime.h"
_SMOKE_OUTPUT_PATH = _FIXTURES_DIR / "go_runtime_module" / "generated.go"
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


def _load_libzstd_required_symbols() -> tuple[str, ...]:
    """Load required function symbol names from profile JSON.

    Returns:
        Required symbol names.

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
    required_functions = raw.get("required_functions")
    if not isinstance(required_functions, list) or not required_functions:
        message = "libzstd profile must define non-empty array `required_functions`."
        raise RuntimeError(message)

    symbols: list[str] = []
    for value in cast("list[object]", required_functions):
        if not isinstance(value, str) or not value:
            message = "libzstd profile `required_functions` must contain non-empty strings."
            raise RuntimeError(message)
        symbols.append(value)
    return tuple(symbols)


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
            lib_id="sample_lib",
            header_path=_SMOKE_HEADER_PATH.resolve(),
            package_name="sample",
            emit_kinds="func,var",
        )
    )

    zstd_header, zstd_cflags = _resolve_libzstd_header_and_cflags()
    zstd_required_symbols = _load_libzstd_required_symbols()
    zstd_func_filter = _build_exact_symbol_regex(zstd_required_symbols)
    zstd_source = _run_purego_gen(
        _PuregoGenInvocation(
            lib_id="zstd",
            header_path=zstd_header,
            package_name="zstdfixture",
            emit_kinds="func",
            clang_args=zstd_cflags,
            func_filter=zstd_func_filter,
        )
    )
    return {
        _SMOKE_OUTPUT_PATH: smoke_source,
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
    _write_line("run: PYTHONPATH=src uv run python scripts/update-go-fixture-placeholders.py")
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
