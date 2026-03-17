# Copyright (c) 2026 purego-gen contributors.

"""Golden case loader and runner for generated-source verification."""

from __future__ import annotations

import difflib
import os
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from purego_gen.config_load import resolve_generator_config
from purego_gen.config_model import EnvIncludeHeaders, LocalHeaders
from purego_gen.generation_pipeline import (
    ClangParserError,
    RendererError,
    parse_and_filter,
    render_formatted_go_source,
)
from purego_gen.process_exec import run_command
from purego_gen.toolchain import resolve_c_compiler_command
from purego_gen_e2e.golden_cases_config import (
    AppConfig,
    CompileCRuntime,
    EnvLibdirRuntime,
    GoldenConfig,
    RuntimeConfig,
    load_case_config,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_CASES_DIR = Path("tests") / "cases"
_GO_MOD_PATH = Path("go.mod")
_GO_SUM_PATH = Path("go.sum")
_GENERATED_FILE_NAME = "generated.go"
_RUNTIME_TEST_FILE_NAME = "runtime_test.go"
_CONFIG_FILE_NAME = "config.json"
_GO_TEST_SUPPORT_DIR = Path("tests") / "testruntime"


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One discovered golden case directory."""

    case_id: str
    case_dir: Path
    config_path: Path
    generated_path: Path
    runtime_test_path: Path | None
    config: AppConfig


def _resolve_case_runtime(case_dir: Path, golden: GoldenConfig | None) -> GoldenConfig | None:
    runtime_test_path = case_dir / _RUNTIME_TEST_FILE_NAME
    if runtime_test_path.is_file() and (golden is None or golden.runtime is None):
        default_runtime = CompileCRuntime(
            sources=((case_dir / "runtime.c").resolve(),),
            cflags=(),
            ldflags=(),
        )
        return (
            GoldenConfig(runtime=default_runtime)
            if golden is None
            else replace(golden, runtime=default_runtime)
        )
    return golden


def _load_case(case_dir: Path) -> GoldenCase:
    config_path = case_dir / _CONFIG_FILE_NAME
    app_config = load_case_config(config_path)
    runtime_test_path = case_dir / _RUNTIME_TEST_FILE_NAME
    normalized_runtime_test_path = runtime_test_path if runtime_test_path.is_file() else None
    normalized_config = replace(
        app_config,
        golden=_resolve_case_runtime(case_dir, app_config.golden),
    )
    return GoldenCase(
        case_id=case_dir.name,
        case_dir=case_dir,
        config_path=config_path,
        generated_path=case_dir / _GENERATED_FILE_NAME,
        runtime_test_path=normalized_runtime_test_path,
        config=normalized_config,
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
    discovered = {path.name: path for path in case_dirs if (path / _CONFIG_FILE_NAME).is_file()}
    if not discovered:
        message = f"no case directories with {_CONFIG_FILE_NAME} found under: {cases_root}"
        raise RuntimeError(message)

    if not selected_case_ids:
        return tuple(_load_case(discovered[case_id]) for case_id in sorted(discovered))

    missing = sorted(case_id for case_id in selected_case_ids if case_id not in discovered)
    if missing:
        message = f"unknown case id(s): {', '.join(missing)}"
        raise RuntimeError(message)

    deduplicated = tuple(dict.fromkeys(selected_case_ids))
    return tuple(_load_case(discovered[case_id]) for case_id in deduplicated)


def render_case_source(case: GoldenCase) -> str:
    """Render generated Go source for one case config.

    Returns:
        Generated and formatted Go source.

    Raises:
        RuntimeError: Config resolution, parsing, filtering, or rendering fails.
    """
    try:
        generator_config = resolve_generator_config(case.config.generator)
        _declarations, filtered_declarations = parse_and_filter(generator_config)
        return render_formatted_go_source(generator_config, filtered_declarations)
    except (ClangParserError, RendererError, ValueError, RuntimeError) as error:
        message = f"case `{case.case_id}` generation failed.\nerror: {error}"
        raise RuntimeError(message) from error


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


def _copy_case_runtime_support_files(*, case: GoldenCase, module_dir: Path) -> None:
    skip_names = {
        _GENERATED_FILE_NAME,
        _CONFIG_FILE_NAME,
    }
    for entry in sorted(case.case_dir.iterdir()):
        if not entry.is_file() or entry.name in skip_names:
            continue
        shutil.copy2(entry, module_dir / entry.name)


def _copy_go_test_support_package(*, repo_root: Path, module_dir: Path) -> None:
    source_dir = repo_root / _GO_TEST_SUPPORT_DIR
    if not source_dir.is_dir():
        message = f"go test support directory not found: {source_dir}"
        raise RuntimeError(message)
    destination_dir = module_dir / _GO_TEST_SUPPORT_DIR
    shutil.copytree(source_dir, destination_dir)


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

    source_paths = [str(source_path) for source_path in runtime.sources]
    for source_path in runtime.sources:
        if not source_path.is_file():
            message = f"case `{case.case_id}` runtime source not found: {source_path}"
            raise RuntimeError(message)

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
        _copy_case_runtime_support_files(case=case, module_dir=module_dir)
        _copy_go_test_support_package(repo_root=repo_root, module_dir=module_dir)

        env = os.environ.copy()
        env["CGO_ENABLED"] = "0"

        if case.runtime_test_path is None:
            command = [go_binary, "test", "-run", "^$", "./..."]
            result = run_command(command, cwd=module_dir, env=env)
            if result.returncode != 0:
                message = f"case `{case.case_id}` compile check failed.\nstderr:\n{result.stderr}"
                raise RuntimeError(message)
            return

        runtime = None if case.config.golden is None else case.config.golden.runtime
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

        # Runtime tests are always compiled. compile_c cases still need one
        # concrete shared-library path, while env_libdir cases use their
        # existing *_LIB_DIR environment variables directly.
        if isinstance(runtime, CompileCRuntime):
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
) -> None:
    """Regenerate and write generated.go for all selected cases."""
    for case in cases:
        generated_source = render_case_source(case)
        case.generated_path.parent.mkdir(parents=True, exist_ok=True)
        case.generated_path.write_text(generated_source, encoding="utf-8")
        _write_line(f"updated: {case.generated_path.relative_to(repo_root)}")


def check_cases(
    *,
    cases: Iterable[GoldenCase],
    repo_root: Path,
    strict_head: bool,
) -> None:
    """Run generation, golden diff, and go test checks for all selected cases.

    Raises:
        RuntimeError: Generation, drift detection, or go test validation fails.
    """
    for case in cases:
        _write_line(f"checking: {case.case_id}")
        generated_source = render_case_source(case)
        expected_source = _load_expected_source(
            repo_root=repo_root,
            case=case,
            strict_head=strict_head,
        )
        if generated_source != expected_source:
            diff = _diff_text(
                expected=expected_source,
                actual=generated_source,
                case_id=case.case_id,
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
    "CompileCRuntime",
    "EnvIncludeHeaders",
    "EnvLibdirRuntime",
    "GoldenCase",
    "LocalHeaders",
    "RuntimeConfig",
    "check_cases",
    "discover_cases",
    "render_case_source",
    "resolve_env_libdir_runtime_library",
    "update_cases",
]
