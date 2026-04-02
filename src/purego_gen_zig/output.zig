const std = @import("std");
const declarations = @import("declarations.zig");

pub fn writeReport(
    w: *std.Io.Writer,
    header_path: []const u8,
    clang_args: []const [*:0]const u8,
    decls: *const declarations.CollectedDeclarations,
    sample_size: usize,
) !void {
    try w.print("header={s}\n", .{header_path});

    try w.writeAll("clang_args=");
    for (clang_args, 0..) |arg, i| {
        if (i > 0) try w.writeByte(' ');
        try w.print("{s}", .{std.mem.span(arg)});
    }
    try w.writeByte('\n');

    try w.print("functions={d}\n", .{decls.functions.items.len});
    try w.print("typedefs={d}\n", .{decls.typedefs.items.len});

    try w.writeAll("sample_functions:\n");
    const limit = @min(sample_size, decls.functions.items.len);
    for (decls.functions.items[0..limit]) |func| {
        try w.print("  {s}(", .{func.name});
        for (func.parameter_c_types, 0..) |pt, i| {
            if (i > 0) try w.writeAll(", ");
            try w.print("{s}", .{pt});
        }
        try w.print(") -> {s}\n", .{func.result_c_type});
    }
}
