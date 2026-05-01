const std = @import("std");
const builtin = @import("builtin");

// Test-only: relies on `std.testing.io` and `std.testing.tmpDir`, which only
// compile under `builtin.is_test`. Lazy analysis would otherwise mask a
// non-test caller until the function is reached.
comptime {
    std.debug.assert(builtin.is_test);
}

pub fn writeGoldenDiff(
    allocator: std.mem.Allocator,
    case_id: []const u8,
    expected: []const u8,
    actual: []const u8,
) !void {
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();

    const expected_subdir = try std.fmt.allocPrint(allocator, "expected/{s}", .{case_id});
    defer allocator.free(expected_subdir);
    const actual_subdir = try std.fmt.allocPrint(allocator, "actual/{s}", .{case_id});
    defer allocator.free(actual_subdir);

    try tmp.dir.createDirPath(std.testing.io, expected_subdir);
    try tmp.dir.createDirPath(std.testing.io, actual_subdir);

    const expected_file = try std.fmt.allocPrint(allocator, "{s}/generated.go", .{expected_subdir});
    defer allocator.free(expected_file);
    const actual_file = try std.fmt.allocPrint(allocator, "{s}/generated.go", .{actual_subdir});
    defer allocator.free(actual_file);

    try tmp.dir.writeFile(std.testing.io, .{ .sub_path = expected_file, .data = expected });
    try tmp.dir.writeFile(std.testing.io, .{ .sub_path = actual_file, .data = actual });

    if (runDiffTool(allocator, tmp.dir, expected_file, actual_file)) |diff_output| {
        defer allocator.free(diff_output);
        std.debug.print("\ngolden case `{s}` mismatch:\n{s}\n", .{ case_id, diff_output });
    } else |err| {
        std.debug.print(
            "\ngolden case `{s}` mismatch (no diff tool available: {s}); raw bodies follow\n--- expected ---\n{s}\n--- actual ---\n{s}\n",
            .{ case_id, @errorName(err), expected, actual },
        );
    }
}

fn runDiffTool(
    allocator: std.mem.Allocator,
    cwd_dir: std.Io.Dir,
    a_path: []const u8,
    b_path: []const u8,
) ![]u8 {
    const git_argv = [_][]const u8{
        "git", "diff", "--no-index", "--no-color", "-u", "--", a_path, b_path,
    };
    if (try tryRun(allocator, cwd_dir, &git_argv)) |out| return out;

    const diff_argv = [_][]const u8{ "diff", "-u", a_path, b_path };
    if (try tryRun(allocator, cwd_dir, &diff_argv)) |out| return out;

    return error.NoDiffToolAvailable;
}

/// Returns null when the program is missing so the caller can try a fallback.
fn tryRun(
    allocator: std.mem.Allocator,
    cwd_dir: std.Io.Dir,
    argv: []const []const u8,
) !?[]u8 {
    const result = std.process.run(allocator, std.testing.io, .{
        .argv = argv,
        .cwd = .{ .dir = cwd_dir },
    }) catch |err| switch (err) {
        error.FileNotFound => return null,
        else => return err,
    };
    allocator.free(result.stderr);

    switch (result.term) {
        .exited => |code| {
            if (code == 0 or code == 1) return result.stdout;
        },
        else => {},
    }
    allocator.free(result.stdout);
    return error.UnexpectedDiffToolExit;
}

test "runDiffTool: identical files produce empty diff" {
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();
    try tmp.dir.writeFile(std.testing.io, .{ .sub_path = "a", .data = "hello\nworld\n" });
    try tmp.dir.writeFile(std.testing.io, .{ .sub_path = "b", .data = "hello\nworld\n" });

    const out = try runDiffTool(std.testing.allocator, tmp.dir, "a", "b");
    defer std.testing.allocator.free(out);
    try std.testing.expectEqualStrings("", out);
}

test "runDiffTool: differing files produce unified diff hunk" {
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();
    try tmp.dir.writeFile(std.testing.io, .{ .sub_path = "a", .data = "one\ntwo\nthree\n" });
    try tmp.dir.writeFile(std.testing.io, .{ .sub_path = "b", .data = "one\nTWO\nthree\n" });

    const out = try runDiffTool(std.testing.allocator, tmp.dir, "a", "b");
    defer std.testing.allocator.free(out);

    try std.testing.expect(std.mem.indexOf(u8, out, "@@") != null);
    try std.testing.expect(std.mem.indexOf(u8, out, "-two") != null);
    try std.testing.expect(std.mem.indexOf(u8, out, "+TWO") != null);
}
