const std = @import("std");
const parser = @import("parser.zig");
const declarations = @import("declarations.zig");
const output = @import("output.zig");

const Args = struct {
    header_path: ?[:0]const u8 = null,
    clang_args: std.ArrayListUnmanaged([*:0]const u8) = .{},
    sample_size: usize = 12,

    fn deinit(self: *Args, allocator: std.mem.Allocator) void {
        self.clang_args.deinit(allocator);
    }
};

fn parseArgs(allocator: std.mem.Allocator) !Args {
    var args = Args{};
    errdefer args.deinit(allocator);

    var iter = try std.process.argsWithAllocator(allocator);
    defer iter.deinit();
    _ = iter.next(); // skip program name

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

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    var args = parseArgs(allocator) catch |err| switch (err) {
        error.InvalidArgs => {
            std.debug.print("usage: purego-gen-zig --header-path <path> [--clang-arg <arg>]... [--sample-size <n>]\n", .{});
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
    var stdout_file = std.fs.File.stdout().writer(&buf);
    const w = &stdout_file.interface;
    try output.writeReport(w, header_path, args.clang_args.items, &decls, args.sample_size);
    try w.flush();
}
