# Copyright (c) 2026 purego-gen contributors.
# ruff: noqa: DOC201, TC003

"""Helpers for building purego-gen CLI invocation commands."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from purego_gen.model import TypeMappingOptions


@dataclass(frozen=True, slots=True)
class PuregoGenInvocation:
    """One purego-gen command configuration."""

    lib_id: str
    header_paths: tuple[Path, ...]
    package_name: str
    emit_kinds: str
    clang_args: tuple[str, ...] = ()
    func_filter: str | None = None
    type_filter: str | None = None
    const_filter: str | None = None
    var_filter: str | None = None
    type_mapping: TypeMappingOptions = field(default_factory=TypeMappingOptions)


def append_optional_filter_flags(command: list[str], *, invocation: PuregoGenInvocation) -> None:
    """Append optional declaration-filter flags."""
    if invocation.func_filter is not None:
        command.extend(["--func-filter", invocation.func_filter])
    if invocation.type_filter is not None:
        command.extend(["--type-filter", invocation.type_filter])
    if invocation.const_filter is not None:
        command.extend(["--const-filter", invocation.const_filter])
    if invocation.var_filter is not None:
        command.extend(["--var-filter", invocation.var_filter])


def append_type_mapping_flags(command: list[str], *, type_mapping: TypeMappingOptions) -> None:
    """Append enabled type-mapping option flags."""
    if type_mapping.const_char_as_string:
        command.append("--const-char-as-string")
    if type_mapping.strict_enum_typedefs:
        command.append("--strict-enum-typedefs")
    if type_mapping.typed_sentinel_constants:
        command.append("--typed-sentinel-constants")


def build_purego_gen_command(
    invocation: PuregoGenInvocation,
    *,
    python_executable: str,
) -> list[str]:
    """Build a `python -m purego_gen ...` command."""
    command = [
        python_executable,
        "-m",
        "purego_gen",
        "--lib-id",
        invocation.lib_id,
        "--pkg",
        invocation.package_name,
        "--emit",
        invocation.emit_kinds,
    ]
    for header_path in invocation.header_paths:
        command.extend(["--header", str(header_path)])
    append_optional_filter_flags(command, invocation=invocation)
    append_type_mapping_flags(command, type_mapping=invocation.type_mapping)
    if invocation.clang_args:
        command.extend(["--", *invocation.clang_args])
    return command


def build_src_pythonpath_env(*, src_dir: Path) -> dict[str, str]:
    """Build subprocess environment with `src` prepended to `PYTHONPATH`."""
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(src_dir)
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}:{existing_pythonpath}"
    )
    return env
