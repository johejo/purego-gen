const std = @import("std");

/// Render a minimal Go-template-syntax subset to writer.
///
/// Supported syntax:
///   {{.field}}                    variable expansion
///   {{.field.nested}}             nested variable expansion
///   {{range .field}}...{{end}}    iterate slice field (each element is new data context)
///   {{if .field}}...{{else}}...{{end}}       conditional (bool or truthy string/int)
///   {{if not .field}}...{{else}}...{{end}}   negated conditional
///   {{if eq .field "value"}}...{{else}}...{{end}}   string equality conditional
///
/// `tmpl` must be comptime-known; template validation (unknown tags, unclosed
/// braces, missing {{end}}) becomes a compile error.
/// Field access uses `@field(data, name)`, so a missing field is also a
/// compile error.
///
/// Supports {{- ...}}, {{... -}}, and {{- ... -}} whitespace trimming.
///
/// Not supported: {{block}}, pipelines, function calls.
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
    const tag_end = comptime findTagEnd(tmpl, tag_start);
    const tag_info = comptime parseTag(tmpl, tag_start, tag_end);
    const literal_end = comptime if (tag_info.left_trim)
        trimTrailingWhitespace(tmpl, 0, tag_start)
    else
        tag_start;
    if (comptime literal_end > 0) {
        try writer.writeAll(comptime tmpl[0..literal_end]);
    }

    const tag = tag_info.content;
    const after_tag = comptime if (tag_info.right_trim)
        skipLeadingWhitespace(tmpl, tag_info.after)
    else
        tag_info.after;

    if (comptime std.mem.startsWith(u8, tag, "range .")) {
        const field_name = comptime tag["range .".len..];
        const block_info = comptime findBlockBounds(tmpl, after_tag);
        const body_end = comptime block_info.else_start orelse block_info.end_start;
        const body_left_trim = comptime if (block_info.else_start != null) block_info.body_left_trim else block_info.end_left_trim;
        const body_limit = comptime if (body_left_trim)
            trimTrailingWhitespace(tmpl, after_tag, body_end)
        else
            body_end;
        const body = comptime tmpl[after_tag..body_limit];
        const else_body = comptime if (block_info.else_start != null)
            tmpl[block_info.else_after..(if (block_info.end_left_trim)
                trimTrailingWhitespace(tmpl, block_info.else_after, block_info.end_start)
            else
                block_info.end_start)]
        else
            "";
        const rest_start = comptime if (block_info.end_right_trim)
            skipLeadingWhitespace(tmpl, block_info.end_after)
        else
            block_info.end_after;
        const rest = comptime tmpl[rest_start..];
        const items = getFieldPath(data, field_name);
        if (items.len == 0 and else_body.len > 0) {
            try render(writer, else_body, data);
        }
        for (items) |item| {
            try render(writer, body, item);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, "if not .")) {
        const field_name = comptime tag["if not .".len..];
        const block_info = comptime findBlockBounds(tmpl, after_tag);
        const body_end = comptime block_info.else_start orelse block_info.end_start;
        const body_left_trim = comptime if (block_info.else_start != null) block_info.body_left_trim else block_info.end_left_trim;
        const body_limit = comptime if (body_left_trim)
            trimTrailingWhitespace(tmpl, after_tag, body_end)
        else
            body_end;
        const body = comptime tmpl[after_tag..body_limit];
        const else_body = comptime if (block_info.else_start != null)
            tmpl[block_info.else_after..(if (block_info.end_left_trim)
                trimTrailingWhitespace(tmpl, block_info.else_after, block_info.end_start)
            else
                block_info.end_start)]
        else
            "";
        const rest_start = comptime if (block_info.end_right_trim)
            skipLeadingWhitespace(tmpl, block_info.end_after)
        else
            block_info.end_after;
        const rest = comptime tmpl[rest_start..];
        if (!isTruthy(getFieldPath(data, field_name))) {
            try render(writer, body, data);
        } else if (else_body.len > 0) {
            try render(writer, else_body, data);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, "if eq .")) {
        const eq_expr = comptime tag["if eq .".len..];
        const separator = comptime std.mem.indexOfScalar(u8, eq_expr, ' ') orelse
            @compileError("gotmpl: expected string literal in eq expression");
        const field_name = comptime eq_expr[0..separator];
        const raw_expected = comptime std.mem.trim(u8, eq_expr[separator + 1 ..], " \t");
        if (comptime raw_expected.len < 2 or raw_expected[0] != '"' or raw_expected[raw_expected.len - 1] != '"') {
            @compileError("gotmpl: eq only supports string literals");
        }
        const expected = comptime raw_expected[1 .. raw_expected.len - 1];
        const block_info = comptime findBlockBounds(tmpl, after_tag);
        const body_end = comptime block_info.else_start orelse block_info.end_start;
        const body_left_trim = comptime if (block_info.else_start != null) block_info.body_left_trim else block_info.end_left_trim;
        const body_limit = comptime if (body_left_trim)
            trimTrailingWhitespace(tmpl, after_tag, body_end)
        else
            body_end;
        const body = comptime tmpl[after_tag..body_limit];
        const else_body = comptime if (block_info.else_start != null)
            tmpl[block_info.else_after..(if (block_info.end_left_trim)
                trimTrailingWhitespace(tmpl, block_info.else_after, block_info.end_start)
            else
                block_info.end_start)]
        else
            "";
        const rest_start = comptime if (block_info.end_right_trim)
            skipLeadingWhitespace(tmpl, block_info.end_after)
        else
            block_info.end_after;
        const rest = comptime tmpl[rest_start..];
        if (eqString(getFieldPath(data, field_name), expected)) {
            try render(writer, body, data);
        } else if (else_body.len > 0) {
            try render(writer, else_body, data);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, "if .")) {
        const field_name = comptime tag["if .".len..];
        const block_info = comptime findBlockBounds(tmpl, after_tag);
        const body_end = comptime block_info.else_start orelse block_info.end_start;
        const body_left_trim = comptime if (block_info.else_start != null) block_info.body_left_trim else block_info.end_left_trim;
        const body_limit = comptime if (body_left_trim)
            trimTrailingWhitespace(tmpl, after_tag, body_end)
        else
            body_end;
        const body = comptime tmpl[after_tag..body_limit];
        const else_body = comptime if (block_info.else_start != null)
            tmpl[block_info.else_after..(if (block_info.end_left_trim)
                trimTrailingWhitespace(tmpl, block_info.else_after, block_info.end_start)
            else
                block_info.end_start)]
        else
            "";
        const rest_start = comptime if (block_info.end_right_trim)
            skipLeadingWhitespace(tmpl, block_info.end_after)
        else
            block_info.end_after;
        const rest = comptime tmpl[rest_start..];
        if (isTruthy(getFieldPath(data, field_name))) {
            try render(writer, body, data);
        } else if (else_body.len > 0) {
            try render(writer, else_body, data);
        }
        try render(writer, rest, data);
    } else if (comptime std.mem.startsWith(u8, tag, ".")) {
        const field_name = comptime tag[1..];
        const rest = comptime tmpl[after_tag..];
        if (comptime field_name.len == 0) {
            try writeValue(writer, data);
        } else {
            try writeValue(writer, getFieldPath(data, field_name));
        }
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
    while (i < s.len) : (i += 1) {
        if (i + 2 < s.len and s[i] == '-' and s[i + 1] == '}' and s[i + 2] == '}') return i;
        if (i + 1 < s.len and s[i] == '}' and s[i + 1] == '}') return i;
    }
    @compileError("gotmpl: unclosed '{{' in template");
}

const BlockBounds = struct {
    else_start: ?usize,
    else_after: usize,
    end_start: usize,
    end_after: usize,
    body_left_trim: bool,
    end_left_trim: bool,
    end_right_trim: bool,
};

/// Returns matching {{else}}/{{end}} positions for the innermost open
/// range/if block starting at `from`. Handles nesting.
/// Emits a compile error if no matching {{end}} is found.
fn findBlockBounds(comptime s: []const u8, comptime from: usize) BlockBounds {
    var depth: usize = 1;
    var pos = from;
    var else_start: ?usize = null;
    var else_after: usize = 0;
    var body_left_trim = false;
    while (pos < s.len) {
        const ts = findTagStart(s, pos);
        if (ts >= s.len) break;
        const te = findTagEnd(s, ts);
        const tag_info = parseTag(s, ts, te);
        const tag = tag_info.content;
        if (std.mem.startsWith(u8, tag, "range .") or
            std.mem.startsWith(u8, tag, "if not .") or
            std.mem.startsWith(u8, tag, "if eq .") or
            std.mem.startsWith(u8, tag, "if ."))
        {
            depth += 1;
        } else if (std.mem.eql(u8, tag, "else")) {
            if (depth == 1) {
                if (else_start != null) @compileError("gotmpl: multiple {{else}} tags in block");
                else_start = ts;
                else_after = if (tag_info.right_trim)
                    skipLeadingWhitespace(s, tag_info.after)
                else
                    tag_info.after;
                body_left_trim = tag_info.left_trim;
            }
        } else if (std.mem.eql(u8, tag, "end")) {
            depth -= 1;
            if (depth == 0) return .{
                .else_start = else_start,
                .else_after = else_after,
                .end_start = ts,
                .end_after = tag_info.after,
                .body_left_trim = body_left_trim,
                .end_left_trim = tag_info.left_trim,
                .end_right_trim = tag_info.right_trim,
            };
        }
        pos = tag_info.after;
    }
    @compileError("gotmpl: missing '{{end}}' in template");
}

const TagInfo = struct {
    content: []const u8,
    left_trim: bool,
    right_trim: bool,
    after: usize,
};

fn parseTag(comptime s: []const u8, comptime tag_start: usize, comptime tag_end: usize) TagInfo {
    const left_trim = s[tag_start + 2] == '-';
    const right_trim = s[tag_end] == '-';

    const content_start = tag_start + 2 + @as(usize, if (left_trim) 1 else 0);
    const content_end = tag_end - @as(usize, if (right_trim) 1 else 0);
    const after = tag_end + 2 + @as(usize, if (right_trim) 1 else 0);
    return .{
        .content = std.mem.trim(u8, s[content_start..content_end], " \t"),
        .left_trim = left_trim,
        .right_trim = right_trim,
        .after = after,
    };
}

fn fieldPathType(comptime T: type, comptime path: []const u8) type {
    const dot_index = comptime std.mem.indexOfScalar(u8, path, '.');
    if (dot_index == null) return @FieldType(T, path);
    const head = comptime path[0..dot_index.?];
    const tail = comptime path[dot_index.? + 1 ..];
    return fieldPathType(@FieldType(T, head), tail);
}

fn getFieldPath(root: anytype, comptime path: []const u8) fieldPathType(@TypeOf(root), path) {
    const dot_index = comptime std.mem.indexOfScalar(u8, path, '.');
    if (dot_index == null) return @field(root, path);
    const head = comptime path[0..dot_index.?];
    const tail = comptime path[dot_index.? + 1 ..];
    return getFieldPath(@field(root, head), tail);
}

fn isTemplateWhitespace(ch: u8) bool {
    return ch == ' ' or ch == '\t' or ch == '\r' or ch == '\n';
}

fn trimTrailingWhitespace(comptime s: []const u8, comptime start: usize, comptime end: usize) comptime_int {
    var i = end;
    while (i > start and isTemplateWhitespace(s[i - 1])) : (i -= 1) {}
    return i;
}

fn skipLeadingWhitespace(comptime s: []const u8, comptime from: usize) comptime_int {
    var i = from;
    while (i < s.len and isTemplateWhitespace(s[i])) : (i += 1) {}
    return i;
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
        .pointer => |pointer| if (pointer.size == .slice) value.len > 0 else @compileError("gotmpl: isTruthy: unsupported pointer type: " ++ @typeName(T)),
        .array => value.len > 0,
        .int, .comptime_int => value != 0,
        .optional => value != null,
        else => @compileError("gotmpl: isTruthy: unsupported type: " ++ @typeName(T)),
    };
}

fn eqString(value: anytype, expected: []const u8) bool {
    const T = @TypeOf(value);
    if (comptime (T == []const u8 or T == []u8 or T == [:0]const u8 or T == [:0]u8)) {
        return std.mem.eql(u8, value, expected);
    }
    @compileError("gotmpl: eq only supports string-like fields, got: " ++ @typeName(T));
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

test "if eq string literal" {
    try expectRender("{{if eq .kind \"block\"}}yes{{else}}no{{end}}", .{ .kind = @as([]const u8, "block") }, "yes");
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

test "trimmed variable removes surrounding whitespace" {
    try expectRender("before \n\t{{- .name -}}\n after", .{ .name = @as([]const u8, "X") }, "beforeXafter");
}

test "left-trimmed variable removes preceding whitespace only" {
    try expectRender("before \n\t{{- .name}}\n after", .{ .name = @as([]const u8, "X") }, "beforeX\n after");
}

test "right-trimmed variable removes following whitespace only" {
    try expectRender("before \n\t{{.name -}}\n after", .{ .name = @as([]const u8, "X") }, "before \n\tXafter");
}

test "trimmed if removes surrounding block whitespace" {
    try expectRender("a \n{{- if .show -}}\n yes \n{{- end -}}\n b", .{ .show = true }, "ayesb");
}

test "left-trimmed if removes block-leading whitespace only" {
    try expectRender("a \n{{- if .show}}yes{{end}} b", .{ .show = true }, "ayes b");
}

test "right-trimmed if removes block-trailing whitespace only" {
    try expectRender("a {{if .show -}}\n yes{{end}} b", .{ .show = true }, "a yes b");
}

test "trimmed range removes surrounding block whitespace" {
    const Item = struct { name: []const u8 };
    const items = [_]Item{ .{ .name = "A" }, .{ .name = "B" } };
    try expectRender("head \n{{- range .items -}}\n{{.name}}\n{{- end -}}\n tail", .{
        .items = @as([]const Item, &items),
    }, "headABtail");
}

test "trimmed nested end matches correct block" {
    const Item = struct { label: []const u8 };
    const items = [_]Item{ .{ .label = "X" }, .{ .label = "Y" } };
    try expectRender(
        "{{- if .ok -}}\n{{- range .items -}}\n[{{.label}}]\n{{- end -}}\n{{- end -}}",
        .{ .ok = true, .items = @as([]const Item, &items) },
        "[X][Y]",
    );
}

test "nested field expansion" {
    try expectRender("{{.outer.name}}", .{ .outer = .{ .name = @as([]const u8, "Alice") } }, "Alice");
}

test "if else branch" {
    try expectRender("{{if .show}}yes{{else}}no{{end}}", .{ .show = false }, "no");
}

test "nested field if else with trimming" {
    try expectRender(
        "a\n{{- if .outer.show -}}\nleft\n{{- else -}}\nright\n{{- end -}}\nb",
        .{ .outer = .{ .show = false } },
        "arightb",
    );
}

test "else can trim following whitespace only" {
    try expectRender(
        "{{if .show}}left{{else -}}\nright{{end}}",
        .{ .show = false },
        "right",
    );
}

test "else can trim preceding whitespace only" {
    try expectRender(
        "{{if .show}}left\n{{- else}}right{{end}}",
        .{ .show = false },
        "right",
    );
}

test "range else branch" {
    const Item = struct { name: []const u8 };
    const items = [_]Item{};
    try expectRender(
        "{{range .items}}{{.name}}{{else}}empty{{end}}",
        .{ .items = @as([]const Item, &items) },
        "empty",
    );
}

test "nested range field access" {
    const Item = struct { value: []const u8 };
    const Group = struct {
        items: []const Item,
    };
    const items = [_]Item{ .{ .value = "A" }, .{ .value = "B" } };
    try expectRender(
        "{{range .group.items}}{{.value}}{{end}}",
        .{ .group = Group{ .items = &items } },
        "AB",
    );
}

test "range right trim and left trimmed end do not leak across nesting" {
    const Item = struct { name: []const u8 };
    const items = [_]Item{ .{ .name = "A" }, .{ .name = "B" } };
    try expectRender(
        "head {{range .items -}}\n{{.name}}\n{{- end}} tail",
        .{ .items = @as([]const Item, &items) },
        "head AB tail",
    );
}
