const std = @import("std");

/// Render a minimal Go-template-syntax subset to writer.
///
/// Supported syntax:
///   {{.field}}                    variable expansion
///   {{range .field}}...{{end}}    iterate slice field (each element is new data context)
///   {{if .field}}...{{end}}       conditional (bool or truthy string/int)
///   {{if not .field}}...{{end}}   negated conditional
///
/// `tmpl` must be comptime-known; template validation (unknown tags, unclosed
/// braces, missing {{end}}) becomes a compile error.
/// Field access uses `@field(data, name)`, so a missing field is also a
/// compile error.
///
/// Not supported: {{- -}} whitespace trimming, {{else}}, {{block}},
/// pipelines, function calls, nested field access ({{.a.b}}).
pub fn render(writer: anytype, comptime tmpl: []const u8, data: anytype) !void {
    @setEvalBranchQuota(1_000_000);
    if (comptime tmpl.len == 0) return;

    const tag_start = comptime findTagStart(tmpl, 0);

    // No tags remaining — write the rest as a literal.
    if (comptime tag_start >= tmpl.len) {
        try writer.writeAll(tmpl);
        return;
    }

    // Write literal prefix before the first tag.
    if (comptime tag_start > 0) {
        try writer.writeAll(comptime tmpl[0..tag_start]);
    }

    const tag_end = comptime findTagEnd(tmpl, tag_start);
    const tag = comptime std.mem.trim(u8, tmpl[tag_start + 2 .. tag_end], " \t");
    const after_tag = comptime tag_end + 2;

    if (comptime std.mem.startsWith(u8, tag, "range .")) {
        const field_name = comptime tag["range .".len..];
        const body_end = comptime findEnd(tmpl, after_tag);
        const body = comptime tmpl[after_tag..body_end];
        const rest = comptime tmpl[body_end + "{{end}}".len ..];
        for (@field(data, field_name)) |item| {
            try render(writer, body, item);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, "if not .")) {
        const field_name = comptime tag["if not .".len..];
        const body_end = comptime findEnd(tmpl, after_tag);
        const body = comptime tmpl[after_tag..body_end];
        const rest = comptime tmpl[body_end + "{{end}}".len ..];
        if (!isTruthy(@field(data, field_name))) {
            try render(writer, body, data);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, "if .")) {
        const field_name = comptime tag["if .".len..];
        const body_end = comptime findEnd(tmpl, after_tag);
        const body = comptime tmpl[after_tag..body_end];
        const rest = comptime tmpl[body_end + "{{end}}".len ..];
        if (isTruthy(@field(data, field_name))) {
            try render(writer, body, data);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, ".")) {
        const field_name = comptime tag[1..];
        const rest = comptime tmpl[after_tag..];
        try writeValue(writer, @field(data, field_name));
        try render(writer, rest, data);
    } else {
        @compileError("gotmpl: unknown tag: {{" ++ tag ++ "}}");
    }
}

// --- comptime helpers ---

/// Returns the index of the first `{{` in s[from..], or s.len if not found.
fn findTagStart(comptime s: []const u8, comptime from: usize) comptime_int {
    var i = from;
    while (i + 1 < s.len) : (i += 1) {
        if (s[i] == '{' and s[i + 1] == '{') return i;
    }
    return s.len;
}

/// Returns the index of the first `}` of the closing `}}` for the tag that
/// opens at tag_start. Emits a compile error if the tag is not closed.
fn findTagEnd(comptime s: []const u8, comptime tag_start: usize) comptime_int {
    var i = tag_start + 2;
    while (i + 1 < s.len) : (i += 1) {
        if (s[i] == '}' and s[i + 1] == '}') return i;
    }
    @compileError("gotmpl: unclosed '{{' in template");
}

/// Returns the index of the `{` that starts the `{{end}}` matching the
/// innermost open range/if block starting at `from`. Handles nesting.
/// Emits a compile error if no matching {{end}} is found.
fn findEnd(comptime s: []const u8, comptime from: usize) comptime_int {
    var depth: usize = 1;
    var pos = from;
    while (pos < s.len) {
        const ts = findTagStart(s, pos);
        if (ts >= s.len) break;
        const te = findTagEnd(s, ts);
        const tag = std.mem.trim(u8, s[ts + 2 .. te], " \t");
        if (std.mem.startsWith(u8, tag, "range .") or
            std.mem.startsWith(u8, tag, "if not .") or
            std.mem.startsWith(u8, tag, "if ."))
        {
            depth += 1;
        } else if (std.mem.eql(u8, tag, "end")) {
            depth -= 1;
            if (depth == 0) return ts;
        }
        pos = te + 2;
    }
    @compileError("gotmpl: missing '{{end}}' in template");
}

// --- runtime helpers ---

fn writeValue(writer: anytype, value: anytype) !void {
    const T = @TypeOf(value);
    if (comptime (T == []const u8 or T == []u8 or T == [:0]const u8 or T == [:0]u8)) {
        try writer.writeAll(value);
    } else if (comptime T == bool) {
        try writer.writeAll(if (value) "true" else "false");
    } else {
        switch (comptime @typeInfo(T)) {
            .int, .comptime_int => try writer.print("{d}", .{value}),
            else => @compileError("gotmpl: writeValue: unsupported type: " ++ @typeName(T)),
        }
    }
}

fn isTruthy(value: anytype) bool {
    const T = @TypeOf(value);
    if (comptime T == bool) return value;
    if (comptime (T == []const u8 or T == []u8 or T == [:0]const u8 or T == [:0]u8)) return value.len > 0;
    return switch (comptime @typeInfo(T)) {
        .int, .comptime_int => value != 0,
        .optional => value != null,
        else => @compileError("gotmpl: isTruthy: unsupported type: " ++ @typeName(T)),
    };
}

// --- tests ---

fn expectRender(comptime tmpl: []const u8, data: anytype, expected: []const u8) !void {
    var buf: std.ArrayList(u8) = .empty;
    defer buf.deinit(std.testing.allocator);
    try render(buf.writer(std.testing.allocator), tmpl, data);
    try std.testing.expectEqualStrings(expected, buf.items);
}

test "empty template" {
    try expectRender("", .{}, "");
}

test "literal only" {
    try expectRender("hello world", .{}, "hello world");
}

test "single variable expansion" {
    try expectRender("Hello, {{.name}}!", .{ .name = @as([]const u8, "Alice") }, "Hello, Alice!");
}

test "multiple variable expansions" {
    try expectRender("{{.a}}-{{.b}}", .{
        .a = @as([]const u8, "foo"),
        .b = @as([]const u8, "bar"),
    }, "foo-bar");
}

test "range over slice of structs" {
    const Item = struct { name: []const u8 };
    const items = [_]Item{ .{ .name = "a" }, .{ .name = "b" }, .{ .name = "c" } };
    try expectRender("{{range .items}}{{.name}},{{end}}", .{
        .items = @as([]const Item, &items),
    }, "a,b,c,");
}

test "empty range" {
    const Item = struct { name: []const u8 };
    const items = [_]Item{};
    try expectRender("{{range .items}}{{.name}}{{end}}suffix", .{
        .items = @as([]const Item, &items),
    }, "suffix");
}

test "if true" {
    try expectRender("{{if .show}}yes{{end}}", .{ .show = true }, "yes");
}

test "if false" {
    try expectRender("{{if .show}}yes{{end}}", .{ .show = false }, "");
}

test "if not true" {
    try expectRender("{{if not .show}}no{{end}}", .{ .show = true }, "");
}

test "if not false" {
    try expectRender("{{if not .show}}no{{end}}", .{ .show = false }, "no");
}

test "nested range inside if" {
    const Item = struct { label: []const u8 };
    const items = [_]Item{ .{ .label = "X" }, .{ .label = "Y" } };
    try expectRender("{{if .ok}}{{range .items}}[{{.label}}]{{end}}{{end}}", .{
        .ok = true,
        .items = @as([]const Item, &items),
    }, "[X][Y]");
}

test "literal text around tags" {
    try expectRender("package {{.pkg}}\n", .{ .pkg = @as([]const u8, "main") }, "package main\n");
}

test "if with non-empty string truthy" {
    try expectRender("{{if .s}}nonempty{{end}}", .{ .s = @as([]const u8, "hello") }, "nonempty");
}

test "if with empty string falsy" {
    try expectRender("{{if .s}}nonempty{{end}}", .{ .s = @as([]const u8, "") }, "");
}
