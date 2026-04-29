const std = @import("std");
const clang = @import("clang.zig");
const parser = @import("parser.zig");
const c = clang.c;

pub const RenderedType = struct {
    text: []const u8,
    comment: ?[]const u8 = null,
    requires_unsafe: bool = false,
    requires_purego: bool = false,
    requires_union_helpers: bool = false,
    rendered_as_alias: bool = false,
};

const go_keywords = std.StaticStringMap(void).initComptime(.{
    .{ "break", {} },
    .{ "case", {} },
    .{ "chan", {} },
    .{ "const", {} },
    .{ "continue", {} },
    .{ "default", {} },
    .{ "defer", {} },
    .{ "else", {} },
    .{ "fallthrough", {} },
    .{ "for", {} },
    .{ "func", {} },
    .{ "go", {} },
    .{ "goto", {} },
    .{ "if", {} },
    .{ "import", {} },
    .{ "interface", {} },
    .{ "map", {} },
    .{ "package", {} },
    .{ "range", {} },
    .{ "return", {} },
    .{ "select", {} },
    .{ "struct", {} },
    .{ "switch", {} },
    .{ "type", {} },
    .{ "var", {} },
});

pub fn dupeString(allocator: std.mem.Allocator, cx_str: c.CXString) ![]const u8 {
    defer c.clang_disposeString(cx_str);
    const slice = parser.clangString(cx_str);
    return allocator.dupe(u8, slice);
}

pub fn dupeCursorRawComment(
    allocator: std.mem.Allocator,
    cursor_arg: c.CXCursor,
) !?[]const u8 {
    const comment_text = c.clang_Cursor_getRawCommentText(cursor_arg);
    defer c.clang_disposeString(comment_text);
    const slice = parser.clangString(comment_text);
    if (slice.len == 0) return null;
    const duped: []const u8 = try allocator.dupe(u8, slice);
    return duped;
}

fn sanitizeIdentifierToken(
    allocator: std.mem.Allocator,
    raw: []const u8,
    fallback: []const u8,
) ![]const u8 {
    const use_fallback = raw.len == 0 or std.mem.eql(u8, raw, "_");
    const source = if (use_fallback) fallback else raw;

    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);

    for (source) |ch| {
        if (std.ascii.isAlphanumeric(ch) or ch == '_') {
            try buffer.append(allocator, ch);
        } else {
            try buffer.append(allocator, '_');
        }
    }

    if (buffer.items.len == 0) {
        try buffer.appendSlice(allocator, fallback);
    }
    if (std.ascii.isDigit(buffer.items[0])) {
        try buffer.insertSlice(allocator, 0, "n_");
    }
    if (go_keywords.has(buffer.items)) {
        try buffer.append(allocator, '_');
    }

    return buffer.toOwnedSlice(allocator);
}

fn nameExists(names: []const []const u8, candidate: []const u8, count: usize) bool {
    for (names[0..count]) |name| {
        if (std.mem.eql(u8, name, candidate)) return true;
    }
    return false;
}

pub fn normalizeParameterNames(
    allocator: std.mem.Allocator,
    param_names: [][]const u8,
) !void {
    for (param_names, 0..) |raw_name, i| {
        const fallback = try std.fmt.allocPrint(allocator, "arg{d}", .{i + 1});
        defer allocator.free(fallback);

        var candidate = try sanitizeIdentifierToken(allocator, raw_name, fallback);
        var suffix: usize = 2;
        while (nameExists(param_names, candidate, i)) {
            const duplicate = candidate;
            candidate = try std.fmt.allocPrint(allocator, "{s}_{d}", .{ duplicate, suffix });
            allocator.free(duplicate);
            suffix += 1;
        }

        allocator.free(raw_name);
        param_names[i] = candidate;
    }
}

fn appendPaddingField(
    w: anytype,
    indent: []const u8,
    padding_bytes: usize,
) !void {
    if (padding_bytes == 0) return;
    try w.print("{s}_ [{d}]byte\n", .{ indent, padding_bytes });
}

pub fn isOpaqueRecordType(record_type: c.CXType) bool {
    const decl = c.clang_getTypeDeclaration(c.clang_getCanonicalType(record_type));
    return c.clang_isCursorDefinition(decl) == 0;
}

pub fn renderFunctionType(
    allocator: std.mem.Allocator,
    fn_type: c.CXType,
) ![]const u8 {
    const result_type = c.clang_getResultType(fn_type);
    const result_rendered = try renderType(allocator, result_type);
    defer freeRenderedType(allocator, result_rendered);

    const num_args = c.clang_getNumArgTypes(fn_type);
    if (num_args < 0) return error.UnsupportedType;

    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;

    try w.writeAll("func(");
    for (0..@as(usize, @intCast(num_args))) |i| {
        if (i > 0) try w.writeAll(", ");
        const arg_type = c.clang_getArgType(fn_type, @intCast(i));
        const arg_rendered = try renderType(allocator, arg_type);
        defer freeRenderedType(allocator, arg_rendered);
        try w.print("{s}", .{arg_rendered.text});
    }
    try w.writeByte(')');
    if (result_rendered.text.len != 0) {
        try w.print(" {s}", .{result_rendered.text});
    }
    return aw.toOwnedSlice();
}

const UnionValidator = struct {};

fn unionFieldCheck(_: *UnionValidator, cursor_arg: c.CXCursor) anyerror!c.enum_CXChildVisitResult {
    if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_FieldDecl) return c.CXChildVisit_Continue;
    if (c.clang_Cursor_isBitField(cursor_arg) != 0) return error.UnsupportedType;
    const field_name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
    if (field_name.len == 0) return error.UnsupportedType;
    return c.CXChildVisit_Continue;
}

const StructFieldContext = struct {
    allocator: std.mem.Allocator,
    writer: *std.Io.Writer,
    indent: []const u8,
    offset_bytes: usize = 0,
    saw_field: bool = false,
};

fn structFieldChildBody(ctx: *StructFieldContext, cursor_arg: c.CXCursor) anyerror!c.enum_CXChildVisitResult {
    if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_FieldDecl) return c.CXChildVisit_Continue;
    if (c.clang_Cursor_isBitField(cursor_arg) != 0) return error.UnsupportedType;
    ctx.saw_field = true;

    const field_name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
    if (field_name.len == 0) return error.UnsupportedType;

    const field_offset_bits = c.clang_Cursor_getOffsetOfField(cursor_arg);
    if (field_offset_bits < 0) return error.UnsupportedType;
    const field_offset: usize = @intCast(@divTrunc(field_offset_bits, 8));
    if (field_offset > ctx.offset_bytes) {
        try appendPaddingField(ctx.writer, ctx.indent, field_offset - ctx.offset_bytes);
    }

    const field_rendered = try renderType(ctx.allocator, c.clang_getCursorType(cursor_arg));
    defer freeRenderedType(ctx.allocator, field_rendered);

    if (field_rendered.comment) |comment| {
        try ctx.writer.print("{s}// C: {s}\n", .{ ctx.indent, comment });
    }
    try ctx.writer.print("{s}{s} {s}\n", .{ ctx.indent, field_name, field_rendered.text });

    const field_size = c.clang_Type_getSizeOf(c.clang_getCanonicalType(c.clang_getCursorType(cursor_arg)));
    if (field_size < 0) return error.UnsupportedType;
    ctx.offset_bytes = field_offset + @as(usize, @intCast(field_size));
    return c.CXChildVisit_Continue;
}

pub fn renderRecordBody(
    allocator: std.mem.Allocator,
    record_type: c.CXType,
    indent: []const u8,
) !RenderedType {
    const canonical = c.clang_getCanonicalType(record_type);
    const decl = c.clang_getTypeDeclaration(canonical);

    const record_size = c.clang_Type_getSizeOf(canonical);
    const record_align = c.clang_Type_getAlignOf(canonical);
    if (record_size < 0 or record_align < 0) return error.UnsupportedType;

    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;

    const kind = c.clang_getCursorKind(decl);
    if (kind == c.CXCursor_UnionDecl) {
        const anchor_type: []const u8 = switch (record_align) {
            1 => "",
            2 => "int16",
            4 => "int32",
            8 => "int64",
            else => return error.UnsupportedType,
        };

        if (anchor_type.len == 0) {
            try w.print("[{d}]byte", .{@as(usize, @intCast(record_size))});
            return .{
                .text = try aw.toOwnedSlice(),
                .requires_union_helpers = true,
                .rendered_as_alias = true,
            };
        }

        var union_validator: UnionValidator = .{};
        try parser.visitChildren(UnionValidator, unionFieldCheck, decl, &union_validator);

        try w.writeAll("struct {\n");
        try w.print("{s}_ [0]{s}\n", .{ indent, anchor_type });
        try w.print("{s}_ [{d}]byte\n", .{ indent, @as(usize, @intCast(record_size)) });
        try w.print("{s}}}", .{indent[0 .. indent.len - 1]});
        return .{
            .text = try aw.toOwnedSlice(),
            .requires_union_helpers = true,
        };
    }

    if (kind != c.CXCursor_StructDecl) return error.UnsupportedType;

    try w.writeAll("struct {\n");
    var field_ctx = StructFieldContext{
        .allocator = allocator,
        .writer = w,
        .indent = indent,
    };
    try parser.visitChildren(StructFieldContext, structFieldChildBody, decl, &field_ctx);
    if (!field_ctx.saw_field) return error.UnsupportedType;

    const final_size: usize = @intCast(record_size);
    if (final_size > field_ctx.offset_bytes) {
        try appendPaddingField(w, indent, final_size - field_ctx.offset_bytes);
    }
    try w.print("{s}}}", .{indent[0 .. indent.len - 1]});

    return .{
        .text = try aw.toOwnedSlice(),
    };
}

pub fn renderType(
    allocator: std.mem.Allocator,
    type_arg: c.CXType,
) !RenderedType {
    const canonical = c.clang_getCanonicalType(type_arg);

    switch (canonical.kind) {
        c.CXType_Void => return .{ .text = try allocator.dupe(u8, "") },
        c.CXType_SChar, c.CXType_Char_S => return .{ .text = try allocator.dupe(u8, "int8") },
        c.CXType_UChar, c.CXType_Char_U => return .{ .text = try allocator.dupe(u8, "uint8") },
        c.CXType_Int, c.CXType_Enum => return .{ .text = try allocator.dupe(u8, "int32") },
        c.CXType_UInt => return .{ .text = try allocator.dupe(u8, "uint32") },
        c.CXType_Float => return .{ .text = try allocator.dupe(u8, "float32") },
        c.CXType_Double => return .{ .text = try allocator.dupe(u8, "float64") },
        c.CXType_Record => return try renderRecordBody(allocator, canonical, "\t\t"),
        c.CXType_ConstantArray => {
            const element_type = c.clang_getArrayElementType(canonical);
            const element_rendered = try renderType(allocator, element_type);
            defer freeRenderedType(allocator, element_rendered);

            const size = c.clang_getArraySize(canonical);
            if (size < 0) return error.UnsupportedType;

            var aw: std.Io.Writer.Allocating = .init(allocator);
            errdefer aw.deinit();
            const w = &aw.writer;
            try w.print("[{d}]{s}", .{ @as(usize, @intCast(size)), element_rendered.text });
            return .{
                .text = try aw.toOwnedSlice(),
                .comment = if (element_rendered.comment) |comment| try allocator.dupe(u8, comment) else null,
                .requires_unsafe = element_rendered.requires_unsafe,
                .requires_purego = element_rendered.requires_purego,
                .requires_union_helpers = element_rendered.requires_union_helpers,
            };
        },
        c.CXType_Pointer => {
            const pointee = c.clang_getPointeeType(canonical);
            const pointee_canonical = c.clang_getCanonicalType(pointee);
            if (pointee_canonical.kind == c.CXType_FunctionProto or pointee_canonical.kind == c.CXType_FunctionNoProto) {
                return .{
                    .text = try allocator.dupe(u8, "uintptr"),
                    .comment = try allocator.dupe(u8, parser.clangString(c.clang_getTypeSpelling(type_arg))),
                };
            }
            if (pointee_canonical.kind == c.CXType_Char_S and c.clang_isConstQualifiedType(pointee) != 0) {
                return .{
                    .text = try allocator.dupe(u8, "uintptr"),
                    .comment = try allocator.dupe(u8, parser.clangString(c.clang_getTypeSpelling(type_arg))),
                };
            }
            if (pointee_canonical.kind == c.CXType_Void or pointee_canonical.kind == c.CXType_Record) {
                return .{
                    .text = try allocator.dupe(u8, "uintptr"),
                    .comment = if (pointee_canonical.kind == c.CXType_Record and isOpaqueRecordType(pointee_canonical))
                        null
                    else
                        try allocator.dupe(u8, parser.clangString(c.clang_getTypeSpelling(type_arg))),
                };
            }
            return error.UnsupportedType;
        },
        else => return error.UnsupportedType,
    }
}

pub fn freeRenderedType(allocator: std.mem.Allocator, rendered: RenderedType) void {
    allocator.free(rendered.text);
    if (rendered.comment) |comment| allocator.free(comment);
}

pub fn renderAliasDefinition(
    allocator: std.mem.Allocator,
    name: []const u8,
    c_type: []const u8,
    go_type: []const u8,
) ![]const u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;
    try w.print("\t// C: {s}\n", .{c_type});
    try w.print("\t{s} = {s}\n", .{ name, go_type });
    return aw.toOwnedSlice();
}

pub fn renderStructDefinition(
    allocator: std.mem.Allocator,
    name: []const u8,
    go_type: []const u8,
) ![]const u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;
    try w.print("\t{s} {s}\n", .{ name, go_type });
    return aw.toOwnedSlice();
}

pub fn renderCommentedTypeDefinition(
    allocator: std.mem.Allocator,
    name: []const u8,
    c_type: []const u8,
    go_type: []const u8,
) ![]const u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;
    try w.print("\t// C: {s}\n", .{c_type});
    try w.print("\t{s} {s}\n", .{ name, go_type });
    return aw.toOwnedSlice();
}

pub fn renderOpaqueDefinition(
    allocator: std.mem.Allocator,
    name: []const u8,
    c_type: []const u8,
) ![]const u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;
    try w.print("\t// C: {s}\n", .{c_type});
    try w.print("\t{s} struct{{}}\n", .{name});
    return aw.toOwnedSlice();
}

pub fn renderCallbackHelperTypeName(
    allocator: std.mem.Allocator,
    name: []const u8,
) ![]const u8 {
    return std.fmt.allocPrint(allocator, "{s}_func", .{name});
}

pub fn renderCallbackHelperDefinition(
    allocator: std.mem.Allocator,
    helper_type_name: []const u8,
    c_type: []const u8,
    go_signature: []const u8,
) ![]const u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;
    try w.print("\t// C: {s}\n", .{c_type});
    try w.print("\t{s} = {s}\n", .{ helper_type_name, go_signature });
    return aw.toOwnedSlice();
}

pub fn renderCallbackConstructor(
    allocator: std.mem.Allocator,
    typedef_name: []const u8,
    helper_type_name: []const u8,
) ![]const u8 {
    return std.fmt.allocPrint(
        allocator,
        "func new_{s}(fn {s}) {s} {{\n\treturn {s}(purego.NewCallback(fn))\n}}\n",
        .{ typedef_name, helper_type_name, typedef_name, typedef_name },
    );
}
