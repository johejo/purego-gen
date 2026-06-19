//! `inspect` text output. Mirrors the structure of Python's
//! `inspect_cmd._report_declarations` and the `--emit-*-config` / `--list-names`
//! helpers. Output is intentionally line-based and not golden-tested, so the
//! goal is functional/structural parity rather than byte-for-byte equality.

const std = @import("std");
const declarations = @import("declarations.zig");
const inspect_detect = @import("inspect_detect.zig");

const opaque_record_code = "PUREGO_GEN_TYPE_OPAQUE_INCOMPLETE_STRUCT";
const opaque_record_reason = "incomplete struct typedef is treated as opaque handle";

/// Which declaration categories a `--render-emit`-style selection covers.
pub const EmitSelection = struct {
    func: bool = true,
    type: bool = true,
    @"const": bool = true,
    @"var": bool = true,
};

const ReasonCount = struct {
    code: []const u8,
    count: usize,
    first_index: usize,
};

fn reasonCountLessThan(_: void, a: ReasonCount, b: ReasonCount) bool {
    if (a.count != b.count) return a.count > b.count; // descending by count
    return a.first_index < b.first_index; // stable on first appearance
}

fn stringLessThan(_: void, a: []const u8, b: []const u8) bool {
    return std.mem.lessThan(u8, a, b);
}

pub fn writeReport(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    header_path: []const u8,
    clang_args: []const [*:0]const u8,
    decls: *const declarations.CollectedDeclarations,
    sample_size: usize,
) !void {
    try w.writeAll("package=manual\n");
    try w.print("header={s}\n", .{header_path});

    try w.writeAll("clang_args=");
    for (clang_args, 0..) |arg, i| {
        if (i > 0) try w.writeByte(' ');
        try w.print("{s}", .{std.mem.span(arg)});
    }
    try w.writeByte('\n');

    var record_count: usize = 0;
    var opaque_record_count: usize = 0;
    for (decls.typedefs.items) |td| {
        if (td.is_record) record_count += 1;
        if (td.is_opaque_record) opaque_record_count += 1;
    }

    try w.print("functions={d}\n", .{decls.functions.items.len});
    // Python keeps record typedefs in both `typedefs` and `record_typedefs`, so
    // `typedefs` reports the full count, not just non-record typedefs.
    try w.print("typedefs={d}\n", .{decls.typedefs.items.len});
    try w.print("record_typedefs={d}\n", .{record_count});
    try w.print("opaque_record_typedefs={d}\n", .{opaque_record_count});
    try w.print("constants={d}\n", .{decls.constants.items.len});
    try w.print("runtime_vars={d}\n", .{decls.runtime_vars.items.len});
    try w.print("skipped_typedefs={d}\n", .{decls.skipped_typedefs.items.len});

    try writeSkipReasonCounts(arena, w, decls);

    try w.writeAll("sample_functions:\n");
    {
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

    try w.writeAll("sample_skipped_typedefs:\n");
    {
        const limit = @min(sample_size, decls.skipped_typedefs.items.len);
        for (decls.skipped_typedefs.items[0..limit]) |skipped| {
            try w.print("  {s}: {s} :: {s}\n", .{ skipped.name, skipped.reason_code, skipped.reason });
        }
    }

    try w.writeAll("sample_opaque_record_typedefs:\n");
    {
        var printed: usize = 0;
        for (decls.typedefs.items) |td| {
            if (!td.is_opaque_record) continue;
            if (printed >= sample_size) break;
            try w.print("  {s}: {s} :: {s}\n", .{ td.name, opaque_record_code, opaque_record_reason });
            printed += 1;
        }
    }

    const callback_candidates = try inspect_detect.findCallbackCandidates(arena, decls);
    try w.print("callback_candidates={d}\n", .{callback_candidates.len});
    try w.writeAll("sample_callback_candidates:\n");
    {
        const limit = @min(sample_size, callback_candidates.len);
        for (callback_candidates[0..limit]) |candidate| {
            try w.print("  {s}: ", .{candidate.function});
            for (candidate.params, 0..) |param, i| {
                if (i > 0) try w.writeAll(", ");
                try w.print("{s}({s})", .{ param.name, param.c_type });
            }
            try w.writeByte('\n');
        }
    }

    const registration_patterns = try inspect_detect.detectRegistrationPatterns(arena, decls);
    try w.print("callback_registration_patterns={d}\n", .{registration_patterns.len});
    try w.writeAll("sample_callback_registration_patterns:\n");
    {
        const limit = @min(sample_size, registration_patterns.len);
        for (registration_patterns[0..limit]) |pattern| {
            try w.print("  {s}: callback={s}", .{ pattern.function, pattern.callback_param });
            if (pattern.userdata_param) |userdata| try w.print(", userdata={s}", .{userdata});
            if (pattern.destructor_param) |destructor| try w.print(", destructor={s}", .{destructor});
            try w.writeByte('\n');
        }
    }
}

fn writeSkipReasonCounts(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    decls: *const declarations.CollectedDeclarations,
) !void {
    var counts: std.ArrayListUnmanaged(ReasonCount) = .empty;
    for (decls.skipped_typedefs.items) |skipped| {
        for (counts.items) |*entry| {
            if (std.mem.eql(u8, entry.code, skipped.reason_code)) {
                entry.count += 1;
                break;
            }
        } else {
            try counts.append(arena, .{
                .code = skipped.reason_code,
                .count = 1,
                .first_index = counts.items.len,
            });
        }
    }
    std.sort.block(ReasonCount, counts.items, {}, reasonCountLessThan);
    for (counts.items) |entry| {
        try w.print("skip_reason[{s}]={d}\n", .{ entry.code, entry.count });
    }
}

/// Emit a `callback_params` config snippet (JSON, 2-space indent) matching
/// Python's `_emit_callback_config`.
pub fn writeCallbackConfig(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    decls: *const declarations.CollectedDeclarations,
) !void {
    const candidates = try inspect_detect.findCallbackCandidates(arena, decls);
    if (candidates.len == 0) {
        try w.writeAll("callback_params: (none)\n");
        return;
    }
    try w.writeAll("callback_params:\n[\n");
    for (candidates, 0..) |candidate, i| {
        try w.writeAll("  {\n");
        try w.print("    \"function\": \"{s}\",\n", .{candidate.function});
        if (candidate.params.len == 0) {
            try w.writeAll("    \"params\": []\n");
        } else {
            try w.writeAll("    \"params\": [\n");
            for (candidate.params, 0..) |param, j| {
                try w.print("      \"{s}\"", .{param.name});
                try w.writeAll(if (j + 1 < candidate.params.len) ",\n" else "\n");
            }
            try w.writeAll("    ]\n");
        }
        try w.writeAll(if (i + 1 < candidates.len) "  },\n" else "  }\n");
    }
    try w.writeAll("]\n");
}

/// Emit a `buffer_params` config snippet (JSON, 2-space indent) matching
/// Python's `_emit_buffer_config`.
pub fn writeBufferConfig(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    decls: *const declarations.CollectedDeclarations,
) !void {
    const candidates = try inspect_detect.findBufferCandidates(arena, decls);
    if (candidates.len == 0) {
        try w.writeAll("buffer_params: (none)\n");
        return;
    }
    try w.writeAll("buffer_params:\n[\n");
    for (candidates, 0..) |candidate, i| {
        try w.writeAll("  {\n");
        try w.print("    \"function\": \"{s}\",\n", .{candidate.function});
        try w.writeAll("    \"pairs\": [\n");
        for (candidate.pairs, 0..) |pair, j| {
            try w.writeAll("      {\n");
            try w.print("        \"pointer\": \"{s}\",\n", .{pair.pointer});
            try w.print("        \"length\": \"{s}\"\n", .{pair.length});
            try w.writeAll(if (j + 1 < candidate.pairs.len) "      },\n" else "      }\n");
        }
        try w.writeAll("    ]\n");
        try w.writeAll(if (i + 1 < candidates.len) "  },\n" else "  }\n");
    }
    try w.writeAll("]\n");
}

/// Emit an `exclude` config snippet (JSON, 2-space indent) matching Python's
/// `_emit_exclude_config`. Only categories present in `emit` are included.
pub fn writeExcludeConfig(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    decls: *const declarations.CollectedDeclarations,
    emit: EmitSelection,
) !void {
    const Category = struct { key: []const u8, names: []const []const u8 };
    var categories: std.ArrayListUnmanaged(Category) = .empty;

    if (emit.func) {
        const names = try sortedNames(arena, try functionNames(arena, decls));
        if (names.len > 0) try categories.append(arena, .{ .key = "func", .names = names });
    }
    if (emit.type) {
        const names = try sortedNames(arena, try typeNames(arena, decls));
        if (names.len > 0) try categories.append(arena, .{ .key = "type", .names = names });
    }
    if (emit.@"const") {
        const names = try sortedNames(arena, try constantNames(arena, decls));
        if (names.len > 0) try categories.append(arena, .{ .key = "const", .names = names });
    }
    if (emit.@"var") {
        const names = try sortedNames(arena, try runtimeVarNames(arena, decls));
        if (names.len > 0) try categories.append(arena, .{ .key = "var", .names = names });
    }

    if (categories.items.len == 0) {
        try w.writeAll("exclude: (none)\n");
        return;
    }
    try w.writeAll("exclude:\n{\n");
    for (categories.items, 0..) |category, i| {
        try w.print("  \"{s}\": [\n", .{category.key});
        for (category.names, 0..) |name, j| {
            try w.print("    \"{s}\"", .{name});
            try w.writeAll(if (j + 1 < category.names.len) ",\n" else "\n");
        }
        try w.writeAll(if (i + 1 < categories.items.len) "  ],\n" else "  ]\n");
    }
    try w.writeAll("}\n");
}

/// Emit sorted declaration names per selected category, matching Python's
/// `_list_declaration_names`.
pub fn writeListNames(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    decls: *const declarations.CollectedDeclarations,
    emit: EmitSelection,
) !void {
    if (emit.func) try writeNameSection(arena, w, "functions", try functionNames(arena, decls));
    if (emit.type) try writeNameSection(arena, w, "types", try typeNames(arena, decls));
    if (emit.@"const") try writeNameSection(arena, w, "constants", try constantNames(arena, decls));
    if (emit.@"var") try writeNameSection(arena, w, "variables", try runtimeVarNames(arena, decls));
}

fn writeNameSection(
    arena: std.mem.Allocator,
    w: *std.Io.Writer,
    label: []const u8,
    names: []const []const u8,
) !void {
    const sorted = try sortedNames(arena, names);
    try w.print("{s}: ({d})\n", .{ label, sorted.len });
    for (sorted) |name| try w.print("  {s}\n", .{name});
}

fn sortedNames(arena: std.mem.Allocator, names: []const []const u8) ![]const []const u8 {
    const copy = try arena.dupe([]const u8, names);
    std.sort.block([]const u8, copy, {}, stringLessThan);
    return copy;
}

fn functionNames(arena: std.mem.Allocator, decls: *const declarations.CollectedDeclarations) ![]const []const u8 {
    var names = try arena.alloc([]const u8, decls.functions.items.len);
    for (decls.functions.items, 0..) |func, i| names[i] = func.name;
    return names;
}

fn typeNames(arena: std.mem.Allocator, decls: *const declarations.CollectedDeclarations) ![]const []const u8 {
    var names = try arena.alloc([]const u8, decls.typedefs.items.len);
    for (decls.typedefs.items, 0..) |td, i| names[i] = td.name;
    return names;
}

fn constantNames(arena: std.mem.Allocator, decls: *const declarations.CollectedDeclarations) ![]const []const u8 {
    var names = try arena.alloc([]const u8, decls.constants.items.len);
    for (decls.constants.items, 0..) |constant, i| names[i] = constant.name;
    return names;
}

fn runtimeVarNames(arena: std.mem.Allocator, decls: *const declarations.CollectedDeclarations) ![]const []const u8 {
    var names = try arena.alloc([]const u8, decls.runtime_vars.items.len);
    for (decls.runtime_vars.items, 0..) |runtime_var, i| names[i] = runtime_var.name;
    return names;
}
