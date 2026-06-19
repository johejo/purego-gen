const std = @import("std");
const parser = @import("parser.zig");
const declarations = @import("declarations.zig");
const output = @import("output.zig");
const golden_cases = @import("golden_cases.zig");
const config_load = @import("config_load.zig");
const gotmpl = @import("gotmpl.zig");
const text_diff = @import("text_diff.zig");

const ArgsIterator = std.process.Args.Iterator;

const InspectArgs = struct {
    header_path: ?[:0]const u8 = null,
    clang_args: std.ArrayListUnmanaged([*:0]const u8) = .empty,
    sample_size: usize = 12,
    skip_gofmt: bool = false,

    fn deinit(self: *InspectArgs, allocator: std.mem.Allocator) void {
        self.clang_args.deinit(allocator);
    }
};

const GenArgs = struct {
    config_path: ?[:0]const u8 = null,
    out_path: [:0]const u8 = "-",
    skip_gofmt: bool = false,
};

fn topUsage() void {
    std.debug.print(
        \\usage: purego-gen-zig <command> [options]
        \\
        \\commands:
        \\  gen      Generate Go bindings from a config file
        \\  inspect  Report parsed declarations for a header
        \\
    , .{});
}

fn genUsage() void {
    std.debug.print(
        "usage: purego-gen-zig gen --config <path|-> [--out <path|->] [--skip-gofmt]\n",
        .{},
    );
}

fn inspectUsage() void {
    std.debug.print(
        "usage: purego-gen-zig inspect --header-path <path> [--clang-arg <arg>]... [--sample-size <n>] [--skip-gofmt]\n",
        .{},
    );
}

fn parseInspectArgs(allocator: std.mem.Allocator, iter: *ArgsIterator) !InspectArgs {
    var args = InspectArgs{};
    errdefer args.deinit(allocator);

    while (iter.next()) |arg| {
        if (std.mem.eql(u8, arg, "--header-path")) {
            args.header_path = iter.next() orelse {
                std.debug.print("error: --header-path requires a value\n", .{});
                return error.InvalidArgs;
            };
        } else if (std.mem.eql(u8, arg, "--clang-arg")) {
            const val = iter.next() orelse {
                std.debug.print("error: --clang-arg requires a value\n", .{});
                return error.InvalidArgs;
            };
            try args.clang_args.append(allocator, val);
        } else if (std.mem.eql(u8, arg, "--skip-gofmt")) {
            args.skip_gofmt = true;
        } else if (std.mem.eql(u8, arg, "--sample-size")) {
            const val = iter.next() orelse {
                std.debug.print("error: --sample-size requires a value\n", .{});
                return error.InvalidArgs;
            };
            args.sample_size = std.fmt.parseInt(usize, val, 10) catch {
                std.debug.print("error: --sample-size must be a non-negative integer\n", .{});
                return error.InvalidArgs;
            };
        } else {
            std.debug.print("error: unknown argument: {s}\n", .{arg});
            return error.InvalidArgs;
        }
    }

    if (args.header_path == null) {
        std.debug.print("error: --header-path is required\n", .{});
        return error.InvalidArgs;
    }

    return args;
}

fn parseGenArgs(iter: *ArgsIterator) !GenArgs {
    var args = GenArgs{};

    while (iter.next()) |arg| {
        if (std.mem.eql(u8, arg, "--config")) {
            args.config_path = iter.next() orelse {
                std.debug.print("error: --config requires a value\n", .{});
                return error.InvalidArgs;
            };
        } else if (std.mem.eql(u8, arg, "--out")) {
            args.out_path = iter.next() orelse {
                std.debug.print("error: --out requires a value\n", .{});
                return error.InvalidArgs;
            };
        } else if (std.mem.eql(u8, arg, "--skip-gofmt")) {
            args.skip_gofmt = true;
        } else {
            std.debug.print("error: unknown argument: {s}\n", .{arg});
            return error.InvalidArgs;
        }
    }

    if (args.config_path == null) {
        std.debug.print("error: --config is required\n", .{});
        return error.InvalidArgs;
    }

    return args;
}

/// Map a config-loading error to a human-readable, CLI-facing message. Returns
/// null for errors without a dedicated message so the caller can fall back to
/// printing the raw error value. Messages are intentionally static (no
/// interpolated values): the offending env-var/path/field is not available as
/// payload on a Zig error.
fn configLoadErrorMessage(err: anyerror) ?[]const u8 {
    return switch (err) {
        error.FileNotFound => "config file not found",
        error.RequiredIncludeDirEnvNotSet => "the include-directory environment variable named by `include_dir_env` is not set",
        error.IncludeDirNotFound => "the include directory from `include_dir_env` does not exist",
        error.MissingGeneratorConfig => "config is missing required field: `generator`",
        error.MissingParseConfig => "config is missing required field: `generator.parse`",
        error.MissingHeadersConfig => "config is missing required field: `generator.parse.headers`",
        error.MissingHeadersKind => "config is missing required field: `generator.parse.headers.kind`",
        error.MissingIncludeDirEnv => "config is missing required field: `generator.parse.headers.include_dir_env`",
        error.MissingHeadersList => "config is missing required field: `generator.parse.headers.headers`",
        error.MissingEmitConfig => "config is missing required field: `generator.emit`",
        error.UnsupportedHeadersKind => "headers.kind must be `local` or `env_include`",
        error.UnsupportedEmitKind => "emit contains an unsupported kind (expected func/type/const/var)",
        else => null,
    };
}

fn loadConfig(
    allocator: std.mem.Allocator,
    init: std.process.Init,
    config_path: [:0]const u8,
) !config_load.LoadedConfig {
    if (std.mem.eql(u8, config_path, "-")) {
        var buf: [4096]u8 = undefined;
        var stdin_reader = std.Io.File.stdin().readerStreaming(init.io, &buf);
        const bytes = try stdin_reader.interface.allocRemaining(allocator, .limited(1024 * 1024));
        defer allocator.free(bytes);
        return config_load.loadFromText(allocator, bytes, ".");
    }
    return config_load.loadFromPath(allocator, config_path);
}

fn runGen(allocator: std.mem.Allocator, init: std.process.Init, iter: *ArgsIterator) !void {
    const args = parseGenArgs(iter) catch |err| switch (err) {
        error.InvalidArgs => {
            genUsage();
            std.process.exit(1);
        },
    };

    const config_path = args.config_path.?;

    var loaded = loadConfig(allocator, init, config_path) catch |err| {
        if (configLoadErrorMessage(err)) |msg| {
            std.debug.print("error: {s}\n", .{msg});
        } else {
            std.debug.print("error: failed to load config: {}\n", .{err});
        }
        std.process.exit(1);
    };
    defer loaded.deinit(allocator);

    const source = config_load.generateSource(allocator, &loaded, args.skip_gofmt) catch |err| {
        std.debug.print("error: failed to generate bindings: {}\n", .{err});
        std.process.exit(1);
    };
    defer allocator.free(source);

    if (std.mem.eql(u8, args.out_path, "-")) {
        var buf: [4096]u8 = undefined;
        var stdout_file = std.Io.File.stdout().writer(init.io, &buf);
        const w = &stdout_file.interface;
        try w.writeAll(source);
        try w.flush();
    } else {
        std.Io.Dir.cwd().writeFile(init.io, .{ .sub_path = args.out_path, .data = source }) catch |err| {
            std.debug.print("error: failed to write output: {}\n", .{err});
            std.process.exit(1);
        };
    }
}

fn runInspect(allocator: std.mem.Allocator, init: std.process.Init, iter: *ArgsIterator) !void {
    var args = parseInspectArgs(allocator, iter) catch |err| switch (err) {
        error.InvalidArgs => {
            inspectUsage();
            std.process.exit(1);
        },
        else => return err,
    };
    defer args.deinit(allocator);

    const header_path = args.header_path.?;

    var tu = parser.parseHeader(header_path, args.clang_args.items) catch |err| {
        std.debug.print("error: failed to parse header: {}\n", .{err});
        std.process.exit(1);
    };
    defer tu.deinit();

    var decls = try declarations.collectDeclarations(allocator, &tu, header_path);
    defer decls.deinit();

    var buf: [4096]u8 = undefined;
    var stdout_file = std.Io.File.stdout().writer(init.io, &buf);
    const w = &stdout_file.interface;
    try output.writeReport(w, header_path, args.clang_args.items, &decls, args.sample_size);
    try w.flush();
}

pub fn main(init: std.process.Init) !void {
    const allocator = init.gpa;

    var iter = try std.process.Args.Iterator.initAllocator(init.minimal.args, allocator);
    defer iter.deinit();
    _ = iter.next(); // skip program name

    const command = iter.next() orelse {
        std.debug.print("error: missing command\n", .{});
        topUsage();
        std.process.exit(1);
    };

    if (std.mem.eql(u8, command, "gen")) {
        try runGen(allocator, init, &iter);
    } else if (std.mem.eql(u8, command, "inspect")) {
        try runInspect(allocator, init, &iter);
    } else {
        std.debug.print("error: unknown command: {s}\n", .{command});
        topUsage();
        std.process.exit(1);
    }
}

test {
    _ = golden_cases;
    _ = config_load;
    _ = gotmpl;
    _ = text_diff;
}
