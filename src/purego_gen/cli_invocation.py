# Copyright (c) 2026 purego-gen contributors.

"""Helpers for building purego-gen CLI invocation commands."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from purego_gen.model import TypeMappingOptions

if TYPE_CHECKING:
    from pathlib import Path


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
    python_executable: str | None = None,
    command_prefix: tuple[str, ...] | None = None,
) -> list[str]:
    """Build a `python -m purego_gen ...` command.

    Returns:
        Tokenized command suitable for process execution.

    Raises:
        ValueError: Neither `python_executable` nor `command_prefix` is provided.
    """
    if command_prefix is None:
        if python_executable is None:
            message = "python_executable is required when command_prefix is not provided."
            raise ValueError(message)
        command = [
            python_executable,
            "-m",
            "purego_gen",
        ]
    else:
        command = [*command_prefix]

    command.extend([
        "--lib-id",
        invocation.lib_id,
        "--pkg",
        invocation.package_name,
        "--emit",
        invocation.emit_kinds,
    ])
    for header_path in invocation.header_paths:
        command.extend(["--header", str(header_path)])
    append_optional_filter_flags(command, invocation=invocation)
    append_type_mapping_flags(command, type_mapping=invocation.type_mapping)
    if invocation.clang_args:
        command.extend(["--", *invocation.clang_args])
    return command


def build_src_pythonpath_env(*, src_dir: Path) -> dict[str, str]:
    """Build process environment with `src` prepended to `PYTHONPATH`.

    Returns:
        Environment mapping used for Python module execution from `src`.
    """
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(src_dir)
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}:{existing_pythonpath}"
    )
    return env
