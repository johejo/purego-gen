# Copyright (c) 2026 purego-gen contributors.

"""Golden case loader and runner for generated-source verification."""

from __future__ import annotations

import difflib
import json
import os
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from golden_cases_schema import (
    CaseProfileInput,
    CompileCRuntimeInput,
    LocalHeadersInput,
)
from pydantic import ValidationError

from purego_gen.cli_invocation import (
    PuregoGenInvocation,
    build_purego_gen_command,
    build_src_pythonpath_env,
)
from purego_gen.model import TypeMappingOptions
from purego_gen.process_exec import run_command
from purego_gen.toolchain import resolve_c_compiler_command
from purego_gen.validation_error_format import format_validation_error

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_CASES_DIR = Path("tests") / "cases"
_GO_MOD_PATH = Path("go.mod")
_GO_SUM_PATH = Path("go.sum")
_GENERATED_FILE_NAME = "generated.go"
_RUNTIME_TEST_FILE_NAME = "runtime_test.go"


@dataclass(frozen=True, slots=True)
class CaseFilters:
    """Optional per-category declaration filters."""

    func: str | None = None
    type_: str | None = None
    const: str | None = None
    var: str | None = None


@dataclass(frozen=True, slots=True)
class LocalHeaders:
    """Header source definition for local case files."""

    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnvIncludeHeaders:
    """Header source definition via include-directory environment variable."""

    include_dir_env: str
    header_names: tuple[str, ...]


HeaderConfig = LocalHeaders | EnvIncludeHeaders


@dataclass(frozen=True, slots=True)
class CompileCRuntime:
    """Runtime library definition by compiling case-local C sources."""

    sources: tuple[str, ...]
    cflags: tuple[str, ...]
    ldflags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnvLibdirRuntime:
    """Runtime library definition via library-directory environment variable."""

    lib_dir_env: str
    library_names: tuple[str, ...]


RuntimeConfig = CompileCRuntime | EnvLibdirRuntime


@dataclass(frozen=True, slots=True)
class CaseProfile:
    """One parsed case profile loaded from profile.json."""

    lib_id: str
    package: str
    emit: str
    headers: HeaderConfig
    filters: CaseFilters
    type_mapping: TypeMappingOptions
    clang_args: tuple[str, ...]
    runtime: RuntimeConfig | None


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One discovered golden case directory."""

    case_id: str
    case_dir: Path
    profile_path: Path
    generated_path: Path
    runtime_test_path: Path | None
    profile: CaseProfile


def _normalize_optional_tuple(value: tuple[str, ...] | None) -> tuple[str, ...]:
    return value if value is not None else ()


def _reject_removed_pkg_config_kinds(raw_profile: object, *, profile_path: Path) -> None:
    if not isinstance(raw_profile, dict):
        return

    profile_dict = cast("dict[str, object]", raw_profile)

    headers = profile_dict.get("headers")
    if isinstance(headers, dict) and cast("dict[str, object]", headers).get("kind") == "pkg_config":
        message = (
            f"profile `{profile_path}` uses removed headers.kind=`pkg_config`; "
            "migrate to headers.kind=`env_include` with "
            "`include_dir_env`+`header_names` or headers.kind=`local`."
        )
        raise RuntimeError(message)

    runtime = profile_dict.get("runtime")
    if isinstance(runtime, dict) and cast("dict[str, object]", runtime).get("kind") == "pkg_config":
        message = (
            f"profile `{profile_path}` uses removed runtime.kind=`pkg_config`; "
            "migrate to runtime.kind=`env_libdir` with "
            "`lib_dir_env`+`library_names` or runtime.kind=`compile_c`."
        )
        raise RuntimeError(message)


def _to_case_profile(profile: CaseProfileInput) -> CaseProfile:
    headers: HeaderConfig
    if isinstance(profile.headers, LocalHeadersInput):
        headers = LocalHeaders(paths=profile.headers.paths)
    else:
        headers = EnvIncludeHeaders(
            include_dir_env=profile.headers.include_dir_env,
            header_names=profile.headers.header_names,
        )

    runtime: RuntimeConfig | None
    if profile.runtime is None:
        runtime = None
    elif isinstance(profile.runtime, CompileCRuntimeInput):
        runtime = CompileCRuntime(
            sources=profile.runtime.sources,
            cflags=_normalize_optional_tuple(profile.runtime.cflags),
            ldflags=_normalize_optional_tuple(profile.runtime.ldflags),
        )
    else:
        runtime = EnvLibdirRuntime(
            lib_dir_env=profile.runtime.lib_dir_env,
            library_names=profile.runtime.library_names,
        )

    return CaseProfile(
        lib_id=profile.lib_id,
        package=profile.package,
        emit=profile.emit,
        headers=headers,
        filters=CaseFilters(
            func=profile.filters.func,
            type_=profile.filters.type_,
            const=profile.filters.const,
            var=profile.filters.var,
        ),
        type_mapping=TypeMappingOptions(
            const_char_as_string=profile.type_mapping.const_char_as_string,
            strict_enum_typedefs=profile.type_mapping.strict_enum_typedefs,
            typed_sentinel_constants=profile.type_mapping.typed_sentinel_constants,
        ),
        clang_args=_normalize_optional_tuple(profile.clang_args),
        runtime=runtime,
    )


def _load_profile(profile_path: Path) -> CaseProfile:
    if not profile_path.is_file():
        message = f"profile not found: {profile_path}"
        raise RuntimeError(message)

    try:
        raw_text = profile_path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"failed to read profile JSON at {profile_path}: {error}"
        raise RuntimeError(message) from error

    try:
        raw_profile = cast("object", json.loads(raw_text))
    except json.JSONDecodeError as error:
        message = (
            f"failed to parse profile JSON at {profile_path}: "
            f"{error.msg} (line {error.lineno}, column {error.colno})"
        )
        raise RuntimeError(message) from error

    _reject_removed_pkg_config_kinds(raw_profile, profile_path=profile_path)

    try:
        profile = CaseProfileInput.model_validate_json(raw_text)
    except ValidationError as error:
        message = format_validation_error(error, context=f"profile `{profile_path}`")
        raise RuntimeError(message) from error

    return _to_case_profile(profile)


def _resolve_case_runtime(case_dir: Path, profile: CaseProfile) -> RuntimeConfig | None:
    runtime_test_path = case_dir / _RUNTIME_TEST_FILE_NAME
    if runtime_test_path.is_file() and profile.runtime is None:
        return CompileCRuntime(sources=("runtime.c",), cflags=(), ldflags=())
    return profile.runtime


def _load_case(case_dir: Path) -> GoldenCase:
    profile_path = case_dir / "profile.json"
    profile = _load_profile(profile_path)
    runtime_test_path = case_dir / _RUNTIME_TEST_FILE_NAME
    normalized_runtime_test_path = runtime_test_path if runtime_test_path.is_file() else None
    normalized_profile = replace(profile, runtime=_resolve_case_runtime(case_dir, profile))
    return GoldenCase(
        case_id=case_dir.name,
        case_dir=case_dir,
        profile_path=profile_path,
        generated_path=case_dir / _GENERATED_FILE_NAME,
        runtime_test_path=normalized_runtime_test_path,
        profile=normalized_profile,
    )


def discover_cases(
    *,
    repo_root: Path,
    selected_case_ids: Sequence[str],
) -> tuple[GoldenCase, ...]:
    """Discover and parse all configured cases under `tests/cases`.

    Returns:
        Parsed case tuple in lexicographic case-id order.

    Raises:
        RuntimeError: Cases directory or selected case IDs are invalid.
    """
    cases_root = repo_root / _CASES_DIR
    if not cases_root.is_dir():
        message = f"cases directory not found: {cases_root}"
        raise RuntimeError(message)

    case_dirs = sorted(path for path in cases_root.iterdir() if path.is_dir())
    discovered = {path.name: path for path in case_dirs if (path / "profile.json").is_file()}
    if not discovered:
        message = f"no case directories with profile.json found under: {cases_root}"
        raise RuntimeError(message)

    if not selected_case_ids:
        return tuple(_load_case(discovered[case_id]) for case_id in sorted(discovered))

    missing = sorted(case_id for case_id in selected_case_ids if case_id not in discovered)
    if missing:
        message = f"unknown case id(s): {', '.join(missing)}"
        raise RuntimeError(message)

    deduplicated = tuple(dict.fromkeys(selected_case_ids))
    return tuple(_load_case(discovered[case_id]) for case_id in deduplicated)


def _resolve_header_paths_and_clang_args(
    case: GoldenCase,
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    profile = case.profile
    if isinstance(profile.headers, LocalHeaders):
        header_paths: list[Path] = []
        for relative_path in profile.headers.paths:
            header_path = (case.case_dir / relative_path).resolve()
            if not header_path.is_file():
                message = f"case `{case.case_id}` header not found: {header_path}"
                raise RuntimeError(message)
            header_paths.append(header_path)
        return tuple(header_paths), profile.clang_args

    include_dir_value = os.environ.get(profile.headers.include_dir_env, "").strip()
    if not include_dir_value:
        message = (
            f"case `{case.case_id}` requires env {profile.headers.include_dir_env} "
            "for headers.kind=`env_include`."
        )
        raise RuntimeError(message)

    include_dir = Path(include_dir_value).expanduser().resolve()
    if not include_dir.is_dir():
        message = (
            f"case `{case.case_id}` include directory from env "
            f"{profile.headers.include_dir_env} does not exist: {include_dir}"
        )
        raise RuntimeError(message)

    header_paths = []
    for header_name in profile.headers.header_names:
        header_path = (include_dir / header_name).resolve()
        if not header_path.is_file():
            message = (
                f"case `{case.case_id}` header not found from env include directory "
                f"{profile.headers.include_dir_env}: {header_path}"
            )
            raise RuntimeError(message)
        header_paths.append(header_path)

    return tuple(header_paths), profile.clang_args


def render_case_source(case: GoldenCase, *, repo_root: Path, python_executable: str) -> str:
    """Render generated Go source for one case profile.

    Returns:
        Rendered source text.

    Raises:
        RuntimeError: Header resolution or generation command execution fails.
    """
    header_paths, clang_args = _resolve_header_paths_and_clang_args(case)

    invocation = PuregoGenInvocation(
        lib_id=case.profile.lib_id,
        header_paths=header_paths,
        package_name=case.profile.package,
        emit_kinds=case.profile.emit,
        clang_args=clang_args,
        func_filter=case.profile.filters.func,
        type_filter=case.profile.filters.type_,
        const_filter=case.profile.filters.const,
        var_filter=case.profile.filters.var,
        type_mapping=case.profile.type_mapping,
    )
    command = build_purego_gen_command(invocation, python_executable=python_executable)
    result = run_command(
        command, cwd=repo_root, env=build_src_pythonpath_env(src_dir=repo_root / "src")
    )
    if result.returncode != 0:
        command_rendered = shlex.join(command)
        message = (
            f"case `{case.case_id}` generation failed.\n"
            f"command: {command_rendered}\n"
            f"stderr:\n{result.stderr}"
        )
        raise RuntimeError(message)
    return result.stdout


def _git_show_head_file(*, repo_root: Path, file_path: Path) -> str | None:
    relative_path = file_path.relative_to(repo_root).as_posix()
    exists_result = run_command(["git", "cat-file", "-e", f"HEAD:{relative_path}"], cwd=repo_root)
    if exists_result.returncode != 0:
        return None
    show_result = run_command(["git", "show", f"HEAD:{relative_path}"], cwd=repo_root)
    if show_result.returncode != 0:
        detail = show_result.stderr.strip() or show_result.stdout.strip() or "git show failed"
        message = f"failed to read HEAD file `{relative_path}`: {detail}"
        raise RuntimeError(message)
    return show_result.stdout


def _load_expected_source(*, repo_root: Path, case: GoldenCase, strict_head: bool) -> str:
    from_head = _git_show_head_file(repo_root=repo_root, file_path=case.generated_path)
    if from_head is not None:
        return from_head

    if strict_head:
        message = f"case `{case.case_id}` generated.go is missing at HEAD in strict mode"
        raise RuntimeError(message)

    if case.generated_path.is_file():
        return case.generated_path.read_text(encoding="utf-8")

    message = f"case `{case.case_id}` generated.go is missing"
    raise RuntimeError(message)


def _write_line(message: str = "") -> None:
    sys.stdout.write(f"{message}\n")


def _find_go_binary() -> str:
    go_binary = shutil.which("go")
    if go_binary is None:
        message = "go is not available in PATH."
        raise RuntimeError(message)
    return go_binary


def resolve_env_libdir_runtime_library(runtime: EnvLibdirRuntime) -> Path:
    """Resolve one shared library path from env_libdir runtime config.

    Returns:
        Resolved shared-library path.

    Raises:
        RuntimeError: Required environment variable or library path is invalid.
    """
    lib_dir_value = os.environ.get(runtime.lib_dir_env, "").strip()
    if not lib_dir_value:
        message = f"required env {runtime.lib_dir_env} is not set for runtime.kind=`env_libdir`."
        raise RuntimeError(message)

    lib_dir = Path(lib_dir_value).expanduser().resolve()
    if not lib_dir.is_dir():
        message = f"lib directory from env {runtime.lib_dir_env} does not exist: {lib_dir}"
        raise RuntimeError(message)

    is_darwin = sys.platform == "darwin"
    for library_name in runtime.library_names:
        stem = library_name if library_name.startswith("lib") else f"lib{library_name}"
        exact_name = f"{stem}.dylib" if is_darwin else f"{stem}.so"
        exact_path = (lib_dir / exact_name).resolve()
        if exact_path.is_file():
            return exact_path
        if not is_darwin:
            matches = sorted(
                path.resolve() for path in lib_dir.glob(f"{stem}.so.*") if path.is_file()
            )
            if matches:
                return matches[0]

    names = ", ".join(runtime.library_names)
    message = (
        f"failed to resolve shared library from env lib directory `{lib_dir}` "
        f"({runtime.lib_dir_env}) for: {names}"
    )
    raise RuntimeError(message)


def _build_runtime_library_for_compile_c(
    *,
    case: GoldenCase,
    runtime: CompileCRuntime,
    output_dir: Path,
) -> Path:
    compiler_command = resolve_c_compiler_command(purpose="compile_c runtime cases")
    output_name = (
        f"libpurego_gen_case_{case.case_id}.dylib"
        if sys.platform == "darwin"
        else f"libpurego_gen_case_{case.case_id}.so"
    )
    output_path = output_dir / output_name

    source_paths: list[str] = []
    for source in runtime.sources:
        source_path = (case.case_dir / source).resolve()
        if not source_path.is_file():
            message = f"case `{case.case_id}` runtime source not found: {source_path}"
            raise RuntimeError(message)
        source_paths.append(str(source_path))

    command = [*compiler_command]
    if sys.platform == "darwin":
        command.append("-dynamiclib")
    else:
        command.extend(["-shared", "-fPIC"])
    default_header_dir = case.case_dir / "headers"
    if default_header_dir.is_dir():
        command.extend(["-I", str(default_header_dir)])
    command.extend(runtime.cflags)
    command.extend(["-o", str(output_path)])
    command.extend(source_paths)
    command.extend(runtime.ldflags)

    result = run_command(command, cwd=case.case_dir)
    if result.returncode != 0:
        message = (
            f"case `{case.case_id}` failed to compile runtime library.\n"
            f"command: {shlex.join(command)}\n"
            f"stderr:\n{result.stderr}"
        )
        raise RuntimeError(message)
    return output_path


def _run_go_test_for_case(
    *,
    case: GoldenCase,
    repo_root: Path,
    generated_source: str,
) -> None:
    go_binary = _find_go_binary()
    go_mod_path = repo_root / _GO_MOD_PATH
    go_sum_path = repo_root / _GO_SUM_PATH
    if not go_mod_path.is_file() or not go_sum_path.is_file():
        message = f"go.mod/go.sum not found at repository root: {go_mod_path} {go_sum_path}"
        raise RuntimeError(message)

    with tempfile.TemporaryDirectory(prefix=f"purego-gen-case-{case.case_id}-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        module_dir = tmp_dir / "module"
        module_dir.mkdir(parents=True, exist_ok=True)

        (module_dir / "go.mod").write_text(
            go_mod_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (module_dir / "go.sum").write_text(
            go_sum_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (module_dir / _GENERATED_FILE_NAME).write_text(generated_source, encoding="utf-8")
        if case.runtime_test_path is not None:
            shutil.copy2(case.runtime_test_path, module_dir / _RUNTIME_TEST_FILE_NAME)

        env = os.environ.copy()
        env["CGO_ENABLED"] = "0"

        if case.runtime_test_path is None:
            command = [go_binary, "test", "-run", "^$", "./..."]
            result = run_command(command, cwd=module_dir, env=env)
            if result.returncode != 0:
                message = f"case `{case.case_id}` compile check failed.\nstderr:\n{result.stderr}"
                raise RuntimeError(message)
            return

        runtime = case.profile.runtime
        if runtime is None:
            message = (
                f"case `{case.case_id}` has runtime_test.go but runtime config "
                "could not be resolved"
            )
            raise RuntimeError(message)

        if isinstance(runtime, CompileCRuntime):
            shared_library_path = _build_runtime_library_for_compile_c(
                case=case,
                runtime=runtime,
                output_dir=tmp_dir,
            )
        else:
            shared_library_path = resolve_env_libdir_runtime_library(runtime)

        env["PUREGO_GEN_TEST_LIB"] = str(shared_library_path)
        command = [go_binary, "test", "./..."]
        result = run_command(command, cwd=module_dir, env=env)
        if result.returncode != 0:
            message = f"case `{case.case_id}` runtime check failed.\nstderr:\n{result.stderr}"
            raise RuntimeError(message)


def _diff_text(*, expected: str, actual: str, case_id: str) -> str:
    diff_lines = difflib.unified_diff(
        expected.splitlines(),
        actual.splitlines(),
        fromfile=f"expected/{case_id}/generated.go",
        tofile=f"actual/{case_id}/generated.go",
        lineterm="",
    )
    return "\n".join(diff_lines)


def update_cases(
    *,
    cases: Iterable[GoldenCase],
    repo_root: Path,
    python_executable: str,
) -> None:
    """Regenerate and write generated.go for all selected cases."""
    for case in cases:
        generated_source = render_case_source(
            case,
            repo_root=repo_root,
            python_executable=python_executable,
        )
        case.generated_path.parent.mkdir(parents=True, exist_ok=True)
        case.generated_path.write_text(generated_source, encoding="utf-8")
        _write_line(f"updated: {case.generated_path.relative_to(repo_root)}")


def check_cases(
    *,
    cases: Iterable[GoldenCase],
    repo_root: Path,
    python_executable: str,
    strict_head: bool,
) -> None:
    """Run generation, golden diff, and go test checks for all selected cases.

    Raises:
        RuntimeError: Generation, golden diff, or go test validation fails.
    """
    for case in cases:
        _write_line(f"checking: {case.case_id}")
        generated_source = render_case_source(
            case,
            repo_root=repo_root,
            python_executable=python_executable,
        )
        expected_source = _load_expected_source(
            repo_root=repo_root, case=case, strict_head=strict_head
        )
        if generated_source != expected_source:
            diff = _diff_text(
                expected=expected_source, actual=generated_source, case_id=case.case_id
            )
            message = (
                f"case `{case.case_id}` golden drift detected.\n"
                f"Run: scripts/uv-run-python-src.sh scripts/golden_cases.py --mode update\n\n"
                f"{diff}"
            )
            raise RuntimeError(message)

        _run_go_test_for_case(case=case, repo_root=repo_root, generated_source=generated_source)
        _write_line(f"ok: {case.case_id}")


__all__ = [
    "GoldenCase",
    "check_cases",
    "discover_cases",
    "resolve_env_libdir_runtime_library",
    "update_cases",
]
