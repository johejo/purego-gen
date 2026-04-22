# Copyright (c) 2026 purego-gen contributors.

"""Check which golden cases currently match the Zig generator output."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import cast

REQUIRED_ENVS = [
    "PUREGO_GEN_LIBCLANG_INCLUDE_DIR",
    "PUREGO_GEN_LIBCLANG_LINK_DIR",
    "PUREGO_GEN_LLVM_LINK_DIR",
    "PUREGO_GEN_ZLIB_LINK_DIR",
    "PUREGO_GEN_LIBCXX_LINK_DIR",
]


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Zig-generated Go source against tests/cases/*/generated.go.",
    )
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        default=[],
        help="Limit to one case id. Repeatable.",
    )
    parser.add_argument(
        "--only-match",
        action="store_true",
        help="Print only matching case ids.",
    )
    parser.add_argument(
        "--skip-gofmt",
        action="store_true",
        help="Skip gofmt formatting (debug: see raw template output).",
    )
    return parser


def _zig_checker_source(selected_case_ids: list[str], *, skip_gofmt: bool = False) -> str:
    case_filter = (
        "const selected_case_ids = [_][]const u8{"
        + "".join(f'\n    "{case_id}",' for case_id in selected_case_ids)
        + "\n};\n"
        if selected_case_ids
        else "const selected_case_ids = [_][]const u8{};\n"
    )
    return f"""const std = @import("std");
const golden_cases = @import("src/purego_gen_zig/golden_cases.zig");

{case_filter}

fn shouldCheck(case_id: []const u8) bool {{
    if (selected_case_ids.len == 0) return true;
    for (selected_case_ids) |selected_case_id| {{
        if (std.mem.eql(u8, case_id, selected_case_id)) return true;
    }}
    return false;
}}

pub fn main(init: std.process.Init) !void {{
    const io = init.io;
    const allocator = init.gpa;

    var dir = try std.Io.Dir.cwd().openDir(io, "tests/cases", .{{ .iterate = true }});
    defer dir.close(io);

    var iter = dir.iterate();
    var stdout_buf: [4096]u8 = undefined;
    var stdout_writer = std.Io.File.stdout().writer(io, &stdout_buf);
    const w = &stdout_writer.interface;

    while (try iter.next(io)) |entry| {{
        if (entry.kind != .directory) continue;
        if (!shouldCheck(entry.name)) continue;

        const case_dir = try std.fs.path.join(allocator, &.{{ "tests/cases", entry.name }});
        defer allocator.free(case_dir);

        const config_path = try std.fs.path.join(allocator, &.{{ case_dir, "config.json" }});
        defer allocator.free(config_path);
        std.Io.Dir.cwd().access(io, config_path, .{{}}) catch continue;

        var loaded = golden_cases.loadCaseFromDir(allocator, case_dir) catch |err| {{
            try w.print("{{s}}\\tLOAD_ERR\\t{{}}\\n", .{{ entry.name, err }});
            continue;
        }};
        defer loaded.deinit(allocator);

        const expected = std.Io.Dir.cwd().readFileAlloc(
            io,
            loaded.expected_path,
            allocator,
            .limited(1024 * 1024),
        ) catch |err| {{
            try w.print("{{s}}\\tEXPECTED_ERR\\t{{}}\\n", .{{ entry.name, err }});
            continue;
        }};
        defer allocator.free(expected);

        const actual = golden_cases.generateCaseSource(
            allocator,
            &loaded,
            {"true" if skip_gofmt else "false"},
        ) catch |err| {{
            try w.print("{{s}}\\tGENERATE_ERR\\t{{}}\\n", .{{ entry.name, err }});
            continue;
        }};
        defer allocator.free(actual);

        if (std.mem.eql(u8, expected, actual)) {{
            try w.print("{{s}}\\tMATCH\\n", .{{entry.name}});
        }} else {{
            try w.print("{{s}}\\tDIFF\\n", .{{entry.name}});
        }}
    }}
    try w.flush();
}}
"""


async def _run_command(command: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout.decode(), stderr.decode()


def _ensure_required_envs(env: dict[str, str]) -> None:
    missing = [name for name in REQUIRED_ENVS if not env.get(name)]
    if missing:
        names = ", ".join(missing)
        message = f"missing required environment variable(s): {names}"
        raise SystemExit(message)


def main() -> int:
    """Compare selected golden cases against Zig generator output.

    Returns:
        Process exit code.
    """
    args = _build_cli().parse_args()
    selected_cases = cast("list[str]", args.cases)
    only_match = cast("bool", args.only_match)
    skip_gofmt = cast("bool", args.skip_gofmt)
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    _ensure_required_envs(env)

    checker_path = repo_root / ".tmp_zig_case_check.zig"
    try:
        checker_path.write_text(
            _zig_checker_source(selected_cases, skip_gofmt=skip_gofmt), encoding="utf-8"
        )
        command = [
            "zig",
            "run",
            str(checker_path),
            "-lc++",
            "-lc",
            "-I",
            env["PUREGO_GEN_LIBCLANG_INCLUDE_DIR"],
            "-L",
            env["PUREGO_GEN_LIBCLANG_LINK_DIR"],
            "-L",
            env["PUREGO_GEN_LLVM_LINK_DIR"],
            "-L",
            env["PUREGO_GEN_ZLIB_LINK_DIR"],
            "-L",
            env["PUREGO_GEN_LIBCXX_LINK_DIR"],
            "-lclang",
            "-lc++",
        ]
        returncode, stdout, stderr = asyncio.run(_run_command(command, repo_root, env))
    finally:
        checker_path.unlink(missing_ok=True)

    if returncode != 0:
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
        return returncode

    if only_match:
        for line in stdout.splitlines():
            case_id, status, *_ = line.split("\t")
            if status == "MATCH":
                sys.stdout.write(f"{case_id}\n")
        return 0

    sys.stdout.write(stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
