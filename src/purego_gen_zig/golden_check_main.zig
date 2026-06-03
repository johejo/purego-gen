const std = @import("std");
const golden_cases = @import("golden_cases.zig");

const Args = struct {
    selected_cases: std.ArrayListUnmanaged([]const u8) = .empty,
    only_match: bool = false,
    skip_gofmt: bool = false,
    help: bool = false,

    fn deinit(self: *Args, allocator: std.mem.Allocator) void {
        for (self.selected_cases.items) |selected_case| {
            allocator.free(selected_case);
        }
        self.selected_cases.deinit(allocator);
    }
};

fn printUsage() void {
    std.debug.print(
        \\usage: purego-gen-zig-golden-check [--case <id>]... [--only-match] [--skip-gofmt]
        \\
    , .{});
}

fn parseArgs(allocator: std.mem.Allocator, process_args: std.process.Args) !Args {
    var args = Args{};
    errdefer args.deinit(allocator);

    var iter = try std.process.Args.Iterator.initAllocator(process_args, allocator);
    defer iter.deinit();
    _ = iter.next(); // skip program name

    while (iter.next()) |arg| {
        if (std.mem.eql(u8, arg, "--case")) {
            const value = iter.next() orelse {
                std.debug.print("error: --case requires a value\n", .{});
                return error.InvalidArgs;
            };
            const owned_value = try allocator.dupe(u8, value);
            errdefer allocator.free(owned_value);
            try args.selected_cases.append(allocator, owned_value);
        } else if (std.mem.startsWith(u8, arg, "--case=")) {
            const value = arg["--case=".len..];
            if (value.len == 0) {
                std.debug.print("error: --case requires a non-empty value\n", .{});
                return error.InvalidArgs;
            }
            const owned_value = try allocator.dupe(u8, value);
            errdefer allocator.free(owned_value);
            try args.selected_cases.append(allocator, owned_value);
        } else if (std.mem.eql(u8, arg, "--only-match")) {
            args.only_match = true;
        } else if (std.mem.eql(u8, arg, "--skip-gofmt")) {
            args.skip_gofmt = true;
        } else if (std.mem.eql(u8, arg, "--help") or std.mem.eql(u8, arg, "-h")) {
            args.help = true;
        } else {
            std.debug.print("error: unknown argument: {s}\n", .{arg});
            return error.InvalidArgs;
        }
    }

    return args;
}

fn shouldCheck(args: Args, case_id: []const u8) bool {
    if (args.selected_cases.items.len == 0) return true;
    for (args.selected_cases.items) |selected_case_id| {
        if (std.mem.eql(u8, case_id, selected_case_id)) return true;
    }
    return false;
}

fn printResult(
    w: anytype,
    args: Args,
    case_id: []const u8,
    status: []const u8,
    err: ?anyerror,
) !void {
    if (args.only_match) {
        if (std.mem.eql(u8, status, "MATCH")) {
            try w.print("{s}\n", .{case_id});
        }
        return;
    }

    if (err) |value| {
        try w.print("{s}\t{s}\t{}\n", .{ case_id, status, value });
    } else {
        try w.print("{s}\t{s}\n", .{ case_id, status });
    }
}

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const allocator = init.gpa;

    var args = parseArgs(allocator, init.minimal.args) catch |err| switch (err) {
        error.InvalidArgs => {
            printUsage();
            std.process.exit(1);
        },
        else => return err,
    };
    defer args.deinit(allocator);

    if (args.help) {
        printUsage();
        return;
    }

    var dir = try std.Io.Dir.cwd().openDir(io, "tests/cases", .{ .iterate = true });
    defer dir.close(io);

    var iter = dir.iterate();
    var stdout_buf: [4096]u8 = undefined;
    var stdout_writer = std.Io.File.stdout().writer(io, &stdout_buf);
    const w = &stdout_writer.interface;

    while (try iter.next(io)) |entry| {
        if (entry.kind != .directory) continue;
        if (!shouldCheck(args, entry.name)) continue;

        const case_dir = try std.fs.path.join(allocator, &.{ "tests/cases", entry.name });
        defer allocator.free(case_dir);

        const config_path = try std.fs.path.join(allocator, &.{ case_dir, "config.json" });
        defer allocator.free(config_path);
        std.Io.Dir.cwd().access(io, config_path, .{}) catch continue;

        var loaded = golden_cases.loadCaseFromDir(allocator, case_dir) catch |err| {
            try printResult(w, args, entry.name, "LOAD_ERR", err);
            continue;
        };
        defer loaded.deinit(allocator);

        const expected = std.Io.Dir.cwd().readFileAlloc(
            io,
            loaded.expected_path,
            allocator,
            .limited(1024 * 1024),
        ) catch |err| {
            try printResult(w, args, entry.name, "EXPECTED_ERR", err);
            continue;
        };
        defer allocator.free(expected);

        const actual = golden_cases.generateCaseSource(
            allocator,
            &loaded,
            args.skip_gofmt,
        ) catch |err| {
            try printResult(w, args, entry.name, "GENERATE_ERR", err);
            continue;
        };
        defer allocator.free(actual);

        if (std.mem.eql(u8, expected, actual)) {
            try printResult(w, args, entry.name, "MATCH", null);
        } else {
            try printResult(w, args, entry.name, "DIFF", null);
        }
    }
    try w.flush();
}
