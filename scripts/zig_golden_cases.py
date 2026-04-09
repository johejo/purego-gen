# Copyright (c) 2026 purego-gen contributors.

"""Check which golden cases currently match the Zig generator output."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


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
    return parser


def _zig_checker_source(selected_case_ids: list[str]) -> str:
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

pub fn main() !void {{
    var gpa = std.heap.GeneralPurposeAllocator(.{{}}){{}};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    var dir = try std.fs.cwd().openDir("tests/cases", .{{ .iterate = true }});
    defer dir.close();

    var iter = dir.iterate();
    var stdout_buf: [4096]u8 = undefined;
    var stdout_writer = std.fs.File.stdout().writer(&stdout_buf);
    const w = &stdout_writer.interface;

    while (try iter.next()) |entry| {{
        if (entry.kind != .directory) continue;
        if (!shouldCheck(entry.name)) continue;

        const case_dir = try std.fs.path.join(allocator, &.{{ "tests/cases", entry.name }});
        defer allocator.free(case_dir);

        const config_path = try std.fs.path.join(allocator, &.{{ case_dir, "config.json" }});
        defer allocator.free(config_path);
        std.fs.cwd().access(config_path, .{{}}) catch continue;

        var loaded = golden_cases.loadCaseFromDir(allocator, case_dir) catch |err| {{
            try w.print("{{s}}\\tLOAD_ERR\\t{{}}\\n", .{{ entry.name, err }});
            continue;
        }};
        defer loaded.deinit(allocator);

        const expected = std.fs.cwd().readFileAlloc(allocator, loaded.expected_path, 1024 * 1024) catch |err| {{
            try w.print("{{s}}\\tEXPECTED_ERR\\t{{}}\\n", .{{ entry.name, err }});
            continue;
        }};
        defer allocator.free(expected);

        const actual = golden_cases.generateCaseSource(allocator, &loaded) catch |err| {{
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


def main() -> int:
    args = _build_cli().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()

    required_envs = [
        "PUREGO_GEN_LIBCLANG_INCLUDE_DIR",
        "PUREGO_GEN_LIBCLANG_LINK_DIR",
        "PUREGO_GEN_LLVM_LINK_DIR",
        "PUREGO_GEN_ZLIB_LINK_DIR",
        "PUREGO_GEN_LIBCXX_LINK_DIR",
    ]
    missing = [name for name in required_envs if not env.get(name)]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"missing required environment variable(s): {names}")

    checker_path = repo_root / ".tmp_zig_case_check.zig"
    try:
        checker_path.write_text(_zig_checker_source(args.cases), encoding="utf-8")
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
        result = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
    finally:
        checker_path.unlink(missing_ok=True)

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")
        return result.returncode

    if args.only_match:
        for line in result.stdout.splitlines():
            case_id, status, *_ = line.split("\t")
            if status == "MATCH":
                print(case_id)
        return 0

    print(result.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
