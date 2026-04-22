const std = @import("std");
const clang = @import("clang.zig");
const parser = @import("parser.zig");
const c = clang.c;

pub const FunctionDecl = struct {
    name: []const u8,
    result_c_type: []const u8,
    parameter_c_types: []const []const u8,
    parameter_names: []const []const u8,
    comment: ?[]const u8 = null,
};

pub const ConstantDecl = struct {
    name: []const u8,
    value_expr: []const u8,
    typed_go_type: ?[]const u8 = null,
    comment: ?[]const u8 = null,
};

pub const RuntimeVarDecl = struct {
    name: []const u8,
    c_type: []const u8,
    comment: ?[]const u8 = null,
};

pub const TypedefDecl = struct {
    name: []const u8,
    c_type: []const u8,
    main_definition: []const u8,
    underlying_go_type: ?[]const u8 = null,
    is_enum_typedef: bool = false,
    comment: ?[]const u8 = null,
    helper_type_definition: ?[]const u8 = null,
    helper_function_definition: ?[]const u8 = null,
    accessor_fields: []const RecordFieldDecl = &.{},
    requires_purego: bool = false,
    requires_unsafe: bool = false,
    requires_union_helpers: bool = false,
};

pub const RecordFieldDecl = struct {
    name: []const u8,
    go_type: []const u8,
    is_union: bool = false,
};

pub const CollectedDeclarations = struct {
    allocator: std.mem.Allocator,
    functions: std.ArrayListUnmanaged(FunctionDecl) = .empty,
    typedefs: std.ArrayListUnmanaged(TypedefDecl) = .empty,
    constants: std.ArrayListUnmanaged(ConstantDecl) = .empty,
    runtime_vars: std.ArrayListUnmanaged(RuntimeVarDecl) = .empty,

    pub fn deinit(self: *CollectedDeclarations) void {
        for (self.functions.items) |func| {
            self.allocator.free(func.name);
            self.allocator.free(func.result_c_type);
            for (func.parameter_c_types) |pt| self.allocator.free(pt);
            self.allocator.free(func.parameter_c_types);
            for (func.parameter_names) |pn| self.allocator.free(pn);
            self.allocator.free(func.parameter_names);
            if (func.comment) |comment| self.allocator.free(comment);
        }
        self.functions.deinit(self.allocator);

        for (self.typedefs.items) |typedef_decl| {
            self.allocator.free(typedef_decl.name);
            self.allocator.free(typedef_decl.c_type);
            self.allocator.free(typedef_decl.main_definition);
            if (typedef_decl.underlying_go_type) |underlying_go_type| self.allocator.free(underlying_go_type);
            if (typedef_decl.comment) |comment| self.allocator.free(comment);
            if (typedef_decl.helper_type_definition) |text| self.allocator.free(text);
            if (typedef_decl.helper_function_definition) |text| self.allocator.free(text);
            for (typedef_decl.accessor_fields) |field| {
                self.allocator.free(field.name);
                self.allocator.free(field.go_type);
            }
            self.allocator.free(typedef_decl.accessor_fields);
        }
        self.typedefs.deinit(self.allocator);

        for (self.constants.items) |constant_decl| {
            self.allocator.free(constant_decl.name);
            self.allocator.free(constant_decl.value_expr);
            if (constant_decl.typed_go_type) |typed_go_type| self.allocator.free(typed_go_type);
            if (constant_decl.comment) |comment| self.allocator.free(comment);
        }
        self.constants.deinit(self.allocator);

        for (self.runtime_vars.items) |runtime_var_decl| {
            self.allocator.free(runtime_var_decl.name);
            self.allocator.free(runtime_var_decl.c_type);
            if (runtime_var_decl.comment) |comment| self.allocator.free(comment);
        }
        self.runtime_vars.deinit(self.allocator);
    }
};

const VisitorContext = struct {
    decls: *CollectedDeclarations,
    header_path: [:0]const u8,
    known_constant_values: std.ArrayListUnmanaged(struct {
        name: []const u8,
        value: u64,
    }) = .empty,
    failed: bool,

    fn deinit(self: *VisitorContext, allocator: std.mem.Allocator) void {
        self.known_constant_values.deinit(allocator);
    }
};

const RenderedType = struct {
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

fn dupeString(allocator: std.mem.Allocator, cx_str: c.CXString) ![]const u8 {
    defer c.clang_disposeString(cx_str);
    const slice = parser.clangString(cx_str);
    return allocator.dupe(u8, slice);
}

fn dupeCursorRawComment(
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

fn normalizeParameterNames(
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

fn isFromTargetHeader(cursor_arg: c.CXCursor, header_path: [:0]const u8) bool {
    const location = c.clang_getCursorLocation(cursor_arg);
    var file: c.CXFile = null;
    c.clang_getExpansionLocation(location, &file, null, null, null);
    if (file == null) return false;
    const file_name = c.clang_getFileName(file);
    defer c.clang_disposeString(file_name);
    const file_str = parser.clangString(file_name);
    return std.mem.eql(u8, file_str, header_path);
}

fn appendPaddingField(
    w: anytype,
    indent: []const u8,
    padding_bytes: usize,
) !void {
    if (padding_bytes == 0) return;
    try w.print("{s}_ [{d}]byte\n", .{ indent, padding_bytes });
}

fn isOpaqueRecordType(record_type: c.CXType) bool {
    const decl = c.clang_getTypeDeclaration(c.clang_getCanonicalType(record_type));
    return c.clang_isCursorDefinition(decl) == 0;
}

fn renderFunctionType(
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

fn renderRecordBody(
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

        const UnionVisitor = struct {
            failed: ?anyerror = null,

            fn callback(
                cursor_arg: c.CXCursor,
                _: c.CXCursor,
                client_data: c.CXClientData,
            ) callconv(.c) c.enum_CXChildVisitResult {
                const ctx: *@This() = @ptrCast(@alignCast(client_data));
                if (ctx.failed != null) return c.CXChildVisit_Break;
                if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_FieldDecl) return c.CXChildVisit_Continue;
                if (c.clang_Cursor_isBitField(cursor_arg) != 0) {
                    ctx.failed = error.UnsupportedType;
                    return c.CXChildVisit_Break;
                }

                const field_name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
                if (field_name.len == 0) {
                    ctx.failed = error.UnsupportedType;
                    return c.CXChildVisit_Break;
                }
                return c.CXChildVisit_Continue;
            }
        };

        var union_visitor = UnionVisitor{};
        _ = c.clang_visitChildren(decl, UnionVisitor.callback, @ptrCast(&union_visitor));
        if (union_visitor.failed) |err| return err;

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
    const StructVisitor = struct {
        allocator: std.mem.Allocator,
        writer: @TypeOf(w),
        indent: []const u8,
        offset_bytes: usize = 0,
        saw_field: bool = false,
        failed: ?anyerror = null,

        fn callback(
            cursor_arg: c.CXCursor,
            _: c.CXCursor,
            client_data: c.CXClientData,
        ) callconv(.c) c.enum_CXChildVisitResult {
            const ctx: *@This() = @ptrCast(@alignCast(client_data));
            if (ctx.failed != null) return c.CXChildVisit_Break;
            if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_FieldDecl) return c.CXChildVisit_Continue;
            if (c.clang_Cursor_isBitField(cursor_arg) != 0) {
                ctx.failed = error.UnsupportedType;
                return c.CXChildVisit_Break;
            }
            ctx.saw_field = true;

            const field_name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
            if (field_name.len == 0) {
                ctx.failed = error.UnsupportedType;
                return c.CXChildVisit_Break;
            }

            const field_offset_bits = c.clang_Cursor_getOffsetOfField(cursor_arg);
            if (field_offset_bits < 0) {
                ctx.failed = error.UnsupportedType;
                return c.CXChildVisit_Break;
            }
            const field_offset: usize = @intCast(@divTrunc(field_offset_bits, 8));
            if (field_offset > ctx.offset_bytes) {
                appendPaddingField(ctx.writer, ctx.indent, field_offset - ctx.offset_bytes) catch |err| {
                    ctx.failed = err;
                    return c.CXChildVisit_Break;
                };
            }

            const field_rendered = renderType(ctx.allocator, c.clang_getCursorType(cursor_arg)) catch |err| {
                ctx.failed = err;
                return c.CXChildVisit_Break;
            };
            defer freeRenderedType(ctx.allocator, field_rendered);

            if (field_rendered.comment) |comment| {
                ctx.writer.print("{s}// C: {s}\n", .{ ctx.indent, comment }) catch |err| {
                    ctx.failed = err;
                    return c.CXChildVisit_Break;
                };
            }
            ctx.writer.print("{s}{s} {s}\n", .{ ctx.indent, field_name, field_rendered.text }) catch |err| {
                ctx.failed = err;
                return c.CXChildVisit_Break;
            };

            const field_size = c.clang_Type_getSizeOf(c.clang_getCanonicalType(c.clang_getCursorType(cursor_arg)));
            if (field_size < 0) {
                ctx.failed = error.UnsupportedType;
                return c.CXChildVisit_Break;
            }
            ctx.offset_bytes = field_offset + @as(usize, @intCast(field_size));
            return c.CXChildVisit_Continue;
        }
    };

    var struct_visitor = StructVisitor{
        .allocator = allocator,
        .writer = w,
        .indent = indent,
    };
    _ = c.clang_visitChildren(decl, StructVisitor.callback, @ptrCast(&struct_visitor));
    if (struct_visitor.failed) |err| return err;
    if (!struct_visitor.saw_field) return error.UnsupportedType;

    const final_size: usize = @intCast(record_size);
    if (final_size > struct_visitor.offset_bytes) {
        try appendPaddingField(w, indent, final_size - struct_visitor.offset_bytes);
    }
    try w.print("{s}}}", .{indent[0 .. indent.len - 1]});

    return .{
        .text = try aw.toOwnedSlice(),
    };
}

fn renderType(
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

fn freeRenderedType(allocator: std.mem.Allocator, rendered: RenderedType) void {
    allocator.free(rendered.text);
    if (rendered.comment) |comment| allocator.free(comment);
}

fn appendKnownConstantValue(
    ctx: *VisitorContext,
    name: []const u8,
    value: u64,
) !void {
    for (ctx.known_constant_values.items) |*entry| {
        if (std.mem.eql(u8, entry.name, name)) {
            entry.value = value;
            return;
        }
    }
    try ctx.known_constant_values.append(ctx.decls.allocator, .{ .name = name, .value = value });
}

fn lookupKnownConstantValue(
    ctx: *const VisitorContext,
    name: []const u8,
) ?u64 {
    for (ctx.known_constant_values.items) |entry| {
        if (std.mem.eql(u8, entry.name, name)) return entry.value;
    }
    return null;
}

fn appendConstant(
    ctx: *VisitorContext,
    name: []const u8,
    value: u64,
    value_expr_override: ?[]const u8,
    typed_go_type: ?[]const u8,
    comment: ?[]const u8,
) !void {
    const decls = ctx.decls;
    for (decls.constants.items) |constant_decl| {
        if (std.mem.eql(u8, constant_decl.name, name)) {
            if (value_expr_override) |value_expr| decls.allocator.free(value_expr);
            if (typed_go_type) |go_type| decls.allocator.free(go_type);
            if (comment) |text| decls.allocator.free(text);
            try appendKnownConstantValue(ctx, constant_decl.name, value);
            return;
        }
    }
    const owned_name = try decls.allocator.dupe(u8, name);
    errdefer decls.allocator.free(owned_name);
    const value_expr = if (value_expr_override) |value_expr|
        value_expr
    else
        try std.fmt.allocPrint(decls.allocator, "{d}", .{value});
    errdefer decls.allocator.free(value_expr);
    errdefer if (typed_go_type) |go_type| decls.allocator.free(go_type);
    errdefer if (comment) |text| decls.allocator.free(text);
    try decls.constants.append(decls.allocator, .{
        .name = owned_name,
        .value_expr = value_expr,
        .typed_go_type = typed_go_type,
        .comment = comment,
    });
    try appendKnownConstantValue(ctx, owned_name, value);
}

fn collectEnumConstants(
    ctx: *VisitorContext,
    enum_decl: c.CXCursor,
) !void {
    const EnumVisitor = struct {
        ctx: *VisitorContext,
        failed: ?anyerror = null,

        fn callback(
            cursor_arg: c.CXCursor,
            _: c.CXCursor,
            client_data: c.CXClientData,
        ) callconv(.c) c.enum_CXChildVisitResult {
            const visitor: *@This() = @ptrCast(@alignCast(client_data));
            if (visitor.failed != null) return c.CXChildVisit_Break;
            if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_EnumConstantDecl) return c.CXChildVisit_Continue;
            appendConstant(
                visitor.ctx,
                parser.clangString(c.clang_getCursorSpelling(cursor_arg)),
                c.clang_getEnumConstantDeclUnsignedValue(cursor_arg),
                null,
                null,
                dupeCursorRawComment(visitor.ctx.decls.allocator, cursor_arg) catch |err| {
                    visitor.failed = err;
                    return c.CXChildVisit_Break;
                },
            ) catch |err| {
                visitor.failed = err;
                return c.CXChildVisit_Break;
            };
            return c.CXChildVisit_Continue;
        }
    };

    var enum_visitor = EnumVisitor{ .ctx = ctx };
    _ = c.clang_visitChildren(enum_decl, EnumVisitor.callback, @ptrCast(&enum_visitor));
    if (enum_visitor.failed) |err| return err;
}

fn normalizeMacroLiteralToken(token: []const u8) ?struct {
    literal: []const u8,
    is_unsigned: bool,
} {
    if (token.len == 0) return null;

    var end = token.len;
    while (end > 0) {
        const ch = token[end - 1];
        if (ch == 'u' or ch == 'U' or ch == 'l' or ch == 'L') {
            end -= 1;
            continue;
        }
        break;
    }
    const literal = token[0..end];
    if (literal.len == 0) return null;

    if (std.mem.startsWith(u8, literal, "0x") or std.mem.startsWith(u8, literal, "0X")) {
        _ = std.fmt.parseUnsigned(u64, literal[2..], 16) catch return null;
    } else {
        _ = std.fmt.parseUnsigned(u64, literal, 10) catch return null;
    }

    var is_unsigned = false;
    for (token[end..]) |ch| {
        if (ch == 'u' or ch == 'U') is_unsigned = true else if (ch != 'l' and ch != 'L') return null;
    }
    return .{ .literal = literal, .is_unsigned = is_unsigned };
}

const MacroOperator = enum {
    add,
    sub,
    mul,
    div,
    mod,
    shl,
    shr,
    bit_or,
    bit_and,
    bit_xor,
    unary_plus,
    unary_minus,
    bit_not,
};

fn macroOperatorPrecedence(op: MacroOperator) u8 {
    return switch (op) {
        .bit_or => 1,
        .bit_xor => 2,
        .bit_and => 3,
        .shl, .shr => 4,
        .add, .sub => 5,
        .mul, .div, .mod => 6,
        .unary_plus, .unary_minus, .bit_not => 7,
    };
}

fn isRightAssociative(op: MacroOperator) bool {
    return switch (op) {
        .unary_plus, .unary_minus, .bit_not => true,
        else => false,
    };
}

const MacroEvalState = struct {
    allocator: std.mem.Allocator,
    values: std.ArrayListUnmanaged(u64) = .empty,
    ops: std.ArrayListUnmanaged(union(enum) { lparen, op: MacroOperator }) = .empty,
    expect_operand: bool = true,

    fn deinit(self: *MacroEvalState) void {
        self.values.deinit(self.allocator);
        self.ops.deinit(self.allocator);
    }
};

fn truncSignedDivide(left: i64, right: i64) ?i64 {
    if (right == 0) return null;
    if (left == std.math.minInt(i64) and right == -1) return null;
    const negative = (left < 0) != (right < 0);
    const left_abs: u64 = if (left < 0) @intCast(-%left) else @intCast(left);
    const right_abs: u64 = if (right < 0) @intCast(-%right) else @intCast(right);
    const quotient = left_abs / right_abs;
    const quotient_i64: i64 = @intCast(quotient);
    return if (negative) -quotient_i64 else quotient_i64;
}

fn truncSignedMod(left: i64, right: i64) ?i64 {
    const quotient = truncSignedDivide(left, right) orelse return null;
    return left - (quotient * right);
}

fn bitcastI64(value: u64) i64 {
    return @bitCast(value);
}

fn bitcastU64(value: i64) u64 {
    return @bitCast(value);
}

fn applyMacroOperator(state: *MacroEvalState, op: MacroOperator) !bool {
    switch (op) {
        .unary_plus, .unary_minus, .bit_not => {
            if (state.values.items.len < 1) return false;
            const operand = state.values.items[state.values.items.len - 1];
            state.values.items.len -= 1;
            const operand_signed = bitcastI64(operand);
            const result = switch (op) {
                .unary_plus => operand,
                .unary_minus => bitcastU64(-%operand_signed),
                .bit_not => ~operand,
                else => unreachable,
            };
            try state.values.append(state.allocator, result);
        },
        else => {
            if (state.values.items.len < 2) return false;
            const right = state.values.items[state.values.items.len - 1];
            state.values.items.len -= 1;
            const left = state.values.items[state.values.items.len - 1];
            state.values.items.len -= 1;
            const left_signed = bitcastI64(left);
            const right_signed = bitcastI64(right);
            const result = switch (op) {
                .add => bitcastU64(left_signed +% right_signed),
                .sub => bitcastU64(left_signed -% right_signed),
                .mul => bitcastU64(left_signed *% right_signed),
                .div => blk: {
                    const value = truncSignedDivide(left_signed, right_signed) orelse return false;
                    break :blk bitcastU64(value);
                },
                .mod => blk: {
                    const value = truncSignedMod(left_signed, right_signed) orelse return false;
                    break :blk bitcastU64(value);
                },
                .shl => blk: {
                    if (right >= 64) return false;
                    break :blk left << @intCast(right);
                },
                .shr => blk: {
                    if (right >= 64) return false;
                    break :blk bitcastU64(left_signed >> @intCast(right));
                },
                .bit_or => left | right,
                .bit_and => left & right,
                .bit_xor => left ^ right,
                else => unreachable,
            };
            try state.values.append(state.allocator, result);
        },
    }
    return true;
}

fn pushMacroOperator(state: *MacroEvalState, op: MacroOperator) !bool {
    const precedence = macroOperatorPrecedence(op);
    while (state.ops.items.len > 0) {
        const top = state.ops.items[state.ops.items.len - 1];
        switch (top) {
            .lparen => break,
            .op => |top_op| {
                const top_precedence = macroOperatorPrecedence(top_op);
                if (top_precedence > precedence or (top_precedence == precedence and !isRightAssociative(op))) {
                    _ = state.ops.pop();
                    if (!try applyMacroOperator(state, top_op)) return false;
                    continue;
                }
                break;
            },
        }
    }
    try state.ops.append(state.allocator, .{ .op = op });
    return true;
}

fn parseMacroOperator(token: []const u8, expect_operand: bool) ?MacroOperator {
    if (std.mem.eql(u8, token, "+")) return if (expect_operand) .unary_plus else .add;
    if (std.mem.eql(u8, token, "-")) return if (expect_operand) .unary_minus else .sub;
    if (std.mem.eql(u8, token, "*")) return if (expect_operand) null else .mul;
    if (std.mem.eql(u8, token, "/")) return if (expect_operand) null else .div;
    if (std.mem.eql(u8, token, "%")) return if (expect_operand) null else .mod;
    if (std.mem.eql(u8, token, "<<")) return if (expect_operand) null else .shl;
    if (std.mem.eql(u8, token, ">>")) return if (expect_operand) null else .shr;
    if (std.mem.eql(u8, token, "|")) return if (expect_operand) null else .bit_or;
    if (std.mem.eql(u8, token, "&")) return if (expect_operand) null else .bit_and;
    if (std.mem.eql(u8, token, "^")) return if (expect_operand) null else .bit_xor;
    if (std.mem.eql(u8, token, "~")) return if (expect_operand) .bit_not else null;
    return null;
}

fn evaluateMacroExpression(
    allocator: std.mem.Allocator,
    tokens: []const []const u8,
    ctx: *const VisitorContext,
) !?u64 {
    var state = MacroEvalState{ .allocator = allocator };
    defer state.deinit();

    for (tokens) |token| {
        if (std.mem.eql(u8, token, "(")) {
            try state.ops.append(allocator, .lparen);
            state.expect_operand = true;
            continue;
        }
        if (std.mem.eql(u8, token, ")")) {
            var found_lparen = false;
            while (state.ops.items.len > 0) {
                const top = state.ops.items[state.ops.items.len - 1];
                state.ops.items.len -= 1;
                switch (top) {
                    .lparen => {
                        found_lparen = true;
                        break;
                    },
                    .op => |op| if (!try applyMacroOperator(&state, op)) return null,
                }
            }
            if (!found_lparen) return null;
            state.expect_operand = false;
            continue;
        }
        if (normalizeMacroLiteralToken(token)) |normalized| {
            const radix: u8 = if (std.mem.startsWith(u8, normalized.literal, "0x") or std.mem.startsWith(u8, normalized.literal, "0X")) 16 else 10;
            const digits = if (radix == 16) normalized.literal[2..] else normalized.literal;
            const value = std.fmt.parseUnsigned(u64, digits, radix) catch return null;
            try state.values.append(allocator, value);
            state.expect_operand = false;
            continue;
        }
        if (lookupKnownConstantValue(ctx, token)) |value| {
            try state.values.append(allocator, value);
            state.expect_operand = false;
            continue;
        }
        const op = parseMacroOperator(token, state.expect_operand) orelse return null;
        if (!try pushMacroOperator(&state, op)) return null;
        state.expect_operand = true;
    }

    if (state.expect_operand) return null;
    while (state.ops.items.len > 0) {
        const top = state.ops.items[state.ops.items.len - 1];
        state.ops.items.len -= 1;
        switch (top) {
            .lparen => return null,
            .op => |op| if (!try applyMacroOperator(&state, op)) return null,
        }
    }
    if (state.values.items.len != 1) return null;
    return state.values.items[0];
}

fn collectMacroDefinition(
    ctx: *VisitorContext,
    cursor_arg: c.CXCursor,
) !void {
    if (c.clang_Cursor_isMacroBuiltin(cursor_arg) != 0) return;
    if (c.clang_Cursor_isMacroFunctionLike(cursor_arg) != 0) return;

    const allocator = ctx.decls.allocator;
    const tu = c.clang_Cursor_getTranslationUnit(cursor_arg);
    const range = c.clang_getCursorExtent(cursor_arg);

    var num_tokens: c_uint = 0;
    var tokens_ptr: [*c]c.CXToken = undefined;
    c.clang_tokenize(tu, range, &tokens_ptr, &num_tokens);
    defer if (num_tokens > 0) c.clang_disposeTokens(tu, tokens_ptr, num_tokens);
    if (num_tokens < 2) return;

    var token_texts = try allocator.alloc([]const u8, num_tokens);
    defer {
        for (token_texts) |text| allocator.free(text);
        allocator.free(token_texts);
    }
    for (0..num_tokens) |i| {
        token_texts[i] = try dupeString(allocator, c.clang_getTokenSpelling(tu, tokens_ptr[i]));
    }

    if (try parseTypedSentinelMacro(ctx, token_texts[1..])) |typed_constant| {
        defer allocator.free(typed_constant.value_expr);
        defer allocator.free(typed_constant.typed_go_type);
        try appendConstant(
            ctx,
            token_texts[0],
            typed_constant.value,
            try allocator.dupe(u8, typed_constant.value_expr),
            try allocator.dupe(u8, typed_constant.typed_go_type),
            null,
        );
        return;
    }

    const value = try evaluateMacroExpression(allocator, token_texts[1..], ctx) orelse return;
    const unsigned_sentinel_go_type = try parseUnsignedSentinelGoType(ctx, token_texts[1..], value);
    try appendConstant(ctx, token_texts[0], value, null, unsigned_sentinel_go_type, null);
}

const TypedSentinelMacro = struct {
    value: u64,
    value_expr: []const u8,
    typed_go_type: []const u8,
};

fn parseUnsignedSentinelGoType(
    ctx: *const VisitorContext,
    tokens: []const []const u8,
    value: u64,
) !?[]const u8 {
    _ = value;
    var saw_unsigned_zero = false;
    var saw_minus = false;
    for (tokens) |token| {
        if (std.mem.eql(u8, token, "-")) {
            saw_minus = true;
            continue;
        }
        if (normalizeMacroLiteralToken(token)) |normalized| {
            if (normalized.is_unsigned and std.mem.eql(u8, normalized.literal, "0")) {
                saw_unsigned_zero = true;
            }
        }
    }
    if (!saw_unsigned_zero or !saw_minus) return null;
    return try ctx.decls.allocator.dupe(u8, "uint64");
}

fn parseTypedSentinelMacro(
    ctx: *const VisitorContext,
    tokens: []const []const u8,
) !?TypedSentinelMacro {
    var expr_buffer: std.ArrayList(u8) = .empty;
    defer expr_buffer.deinit(ctx.decls.allocator);
    for (tokens) |token| {
        try expr_buffer.appendSlice(ctx.decls.allocator, token);
    }
    const expr = expr_buffer.items;
    if (!std.mem.startsWith(u8, expr, "((") or !std.mem.endsWith(u8, expr, ")")) return null;

    const cast_end = std.mem.indexOfScalarPos(u8, expr, 2, ')') orelse return null;
    const type_name = expr[2..cast_end];
    if (type_name.len == 0) return null;

    const sentinel_expr = expr[cast_end + 1 .. expr.len - 1];
    if (std.mem.eql(u8, sentinel_expr, "0")) {
        return .{
            .value = 0,
            .value_expr = try ctx.decls.allocator.dupe(u8, "0"),
            .typed_go_type = try ctx.decls.allocator.dupe(u8, type_name),
        };
    }
    if (std.mem.eql(u8, sentinel_expr, "-1")) {
        return .{
            .value = std.math.maxInt(u64),
            .value_expr = try ctx.decls.allocator.dupe(u8, "^uintptr(0)"),
            .typed_go_type = try ctx.decls.allocator.dupe(u8, type_name),
        };
    }
    return null;
}

fn renderAliasDefinition(
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

fn renderStructDefinition(
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

fn renderCommentedTypeDefinition(
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

fn collectStructAccessorFields(
    allocator: std.mem.Allocator,
    record_type: c.CXType,
) ![]const RecordFieldDecl {
    const canonical = c.clang_getCanonicalType(record_type);
    const decl = c.clang_getTypeDeclaration(canonical);
    const kind = c.clang_getCursorKind(decl);
    if (kind != c.CXCursor_StructDecl and kind != c.CXCursor_UnionDecl) {
        return allocator.alloc(RecordFieldDecl, 0);
    }
    const is_union = kind == c.CXCursor_UnionDecl;

    const AccessorVisitor = struct {
        allocator: std.mem.Allocator,
        is_union: bool,
        fields: std.ArrayListUnmanaged(RecordFieldDecl) = .empty,
        failed: ?anyerror = null,

        fn callback(
            cursor_arg: c.CXCursor,
            _: c.CXCursor,
            client_data: c.CXClientData,
        ) callconv(.c) c.enum_CXChildVisitResult {
            const ctx: *@This() = @ptrCast(@alignCast(client_data));
            if (ctx.failed != null) return c.CXChildVisit_Break;
            if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_FieldDecl) return c.CXChildVisit_Continue;
            if (c.clang_Cursor_isBitField(cursor_arg) != 0) return c.CXChildVisit_Continue;

            const field_name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
            if (field_name.len == 0) return c.CXChildVisit_Continue;

            const rendered = renderType(ctx.allocator, c.clang_getCursorType(cursor_arg)) catch {
                return c.CXChildVisit_Continue;
            };
            defer freeRenderedType(ctx.allocator, rendered);
            if (std.mem.indexOfScalar(u8, rendered.text, '\n') != null) return c.CXChildVisit_Continue;

            ctx.fields.append(ctx.allocator, .{
                .name = ctx.allocator.dupe(u8, field_name) catch |err| {
                    ctx.failed = err;
                    return c.CXChildVisit_Break;
                },
                .go_type = ctx.allocator.dupe(u8, rendered.text) catch |err| {
                    ctx.failed = err;
                    return c.CXChildVisit_Break;
                },
                .is_union = ctx.is_union,
            }) catch |err| {
                ctx.failed = err;
                return c.CXChildVisit_Break;
            };
            return c.CXChildVisit_Continue;
        }
    };

    var visitor = AccessorVisitor{ .allocator = allocator, .is_union = is_union };
    errdefer {
        for (visitor.fields.items) |field| {
            allocator.free(field.name);
            allocator.free(field.go_type);
        }
        visitor.fields.deinit(allocator);
    }
    _ = c.clang_visitChildren(decl, AccessorVisitor.callback, @ptrCast(&visitor));
    if (visitor.failed) |err| return err;
    return visitor.fields.toOwnedSlice(allocator);
}

fn renderOpaqueDefinition(
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

fn renderCallbackHelperTypeName(
    allocator: std.mem.Allocator,
    name: []const u8,
) ![]const u8 {
    return std.fmt.allocPrint(allocator, "{s}_func", .{name});
}

fn renderCallbackHelperDefinition(
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

fn renderCallbackConstructor(
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

fn collectFunction(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    const allocator = ctx.decls.allocator;

    const name = try dupeString(allocator, c.clang_getCursorSpelling(cursor_arg));
    errdefer allocator.free(name);

    const result_type = c.clang_getCursorResultType(cursor_arg);
    const result_c_type = try dupeString(allocator, c.clang_getTypeSpelling(result_type));
    errdefer allocator.free(result_c_type);
    const comment = try dupeCursorRawComment(allocator, cursor_arg);
    errdefer if (comment) |text| allocator.free(text);

    const num_args = c.clang_Cursor_getNumArguments(cursor_arg);
    if (num_args < 0) {
        allocator.free(name);
        allocator.free(result_c_type);
        if (comment) |text| allocator.free(text);
        return;
    }
    const n: usize = @intCast(num_args);

    const param_types = try allocator.alloc([]const u8, n);
    errdefer allocator.free(param_types);
    const param_names = try allocator.alloc([]const u8, n);
    errdefer allocator.free(param_names);

    for (0..n) |i| {
        const arg_cursor = c.clang_Cursor_getArgument(cursor_arg, @intCast(i));
        const arg_type = c.clang_getCursorType(arg_cursor);
        param_types[i] = try dupeString(allocator, c.clang_getTypeSpelling(arg_type));
        param_names[i] = try dupeString(allocator, c.clang_getCursorSpelling(arg_cursor));
    }
    try normalizeParameterNames(allocator, param_names);

    try ctx.decls.functions.append(allocator, .{
        .name = name,
        .result_c_type = result_c_type,
        .parameter_c_types = param_types,
        .parameter_names = param_names,
        .comment = comment,
    });
}

fn collectRuntimeVar(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    if (c.clang_Cursor_getStorageClass(cursor_arg) != c.CX_SC_Extern) return;

    const allocator = ctx.decls.allocator;
    const name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
    if (name.len == 0) return;

    for (ctx.decls.runtime_vars.items) |runtime_var_decl| {
        if (std.mem.eql(u8, runtime_var_decl.name, name)) return;
    }

    try ctx.decls.runtime_vars.append(allocator, .{
        .name = try allocator.dupe(u8, name),
        .c_type = try dupeString(allocator, c.clang_getTypeSpelling(c.clang_getCursorType(cursor_arg))),
        .comment = try dupeCursorRawComment(allocator, cursor_arg),
    });
}

fn collectTypedef(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    const allocator = ctx.decls.allocator;

    const name = try dupeString(allocator, c.clang_getCursorSpelling(cursor_arg));
    errdefer allocator.free(name);

    const underlying = c.clang_getTypedefDeclUnderlyingType(cursor_arg);
    const c_type = try dupeString(allocator, c.clang_getTypeSpelling(underlying));
    errdefer allocator.free(c_type);
    const comment = try dupeCursorRawComment(allocator, cursor_arg);
    errdefer if (comment) |text| allocator.free(text);

    const canonical = c.clang_getCanonicalType(underlying);

    if (canonical.kind == c.CXType_Enum) {
        const enum_decl = c.clang_getTypeDeclaration(canonical);
        try collectEnumConstants(ctx, enum_decl);

        const main_definition = try renderAliasDefinition(allocator, name, c_type, "int32");
        try ctx.decls.typedefs.append(allocator, .{
            .name = name,
            .c_type = c_type,
            .main_definition = main_definition,
            .underlying_go_type = try allocator.dupe(u8, "int32"),
            .is_enum_typedef = true,
            .comment = comment,
        });
        return;
    }

    if (canonical.kind == c.CXType_Record) {
        if (isOpaqueRecordType(canonical)) {
            const main_definition = try renderOpaqueDefinition(allocator, name, c_type);
            try ctx.decls.typedefs.append(allocator, .{
                .name = name,
                .c_type = c_type,
                .main_definition = main_definition,
                .comment = comment,
            });
            return;
        }

        const record_type = renderRecordBody(allocator, canonical, "\t\t") catch {
            allocator.free(name);
            allocator.free(c_type);
            if (comment) |text| allocator.free(text);
            return;
        };
        defer freeRenderedType(allocator, record_type);
        const accessor_fields = collectStructAccessorFields(allocator, canonical) catch {
            allocator.free(name);
            allocator.free(c_type);
            if (comment) |text| allocator.free(text);
            return;
        };
        errdefer {
            for (accessor_fields) |field| {
                allocator.free(field.name);
                allocator.free(field.go_type);
            }
            allocator.free(accessor_fields);
        }
        const main_definition = if (record_type.rendered_as_alias)
            try renderCommentedTypeDefinition(allocator, name, c_type, record_type.text)
        else
            try renderStructDefinition(allocator, name, record_type.text);
        try ctx.decls.typedefs.append(allocator, .{
            .name = name,
            .c_type = c_type,
            .main_definition = main_definition,
            .comment = comment,
            .accessor_fields = accessor_fields,
            .requires_unsafe = record_type.requires_unsafe,
            .requires_purego = record_type.requires_purego,
            .requires_union_helpers = record_type.requires_union_helpers,
        });
        return;
    }

    if (canonical.kind == c.CXType_Pointer) {
        const pointee = c.clang_getPointeeType(canonical);
        const pointee_canonical = c.clang_getCanonicalType(pointee);
        if (pointee_canonical.kind == c.CXType_FunctionProto or pointee_canonical.kind == c.CXType_FunctionNoProto) {
            const main_definition = try renderAliasDefinition(allocator, name, c_type, "uintptr");
            const helper_type_name = try renderCallbackHelperTypeName(allocator, name);
            errdefer allocator.free(helper_type_name);

            const go_signature = try renderFunctionType(allocator, pointee_canonical);
            defer allocator.free(go_signature);

            const helper_type_definition = try renderCallbackHelperDefinition(
                allocator,
                helper_type_name,
                c_type,
                go_signature,
            );
            const helper_function_definition = try renderCallbackConstructor(
                allocator,
                name,
                helper_type_name,
            );
            allocator.free(helper_type_name);

            try ctx.decls.typedefs.append(allocator, .{
                .name = name,
                .c_type = c_type,
                .main_definition = main_definition,
                .comment = comment,
                .helper_type_definition = helper_type_definition,
                .helper_function_definition = helper_function_definition,
                .requires_purego = true,
            });
            return;
        }
    }

    const rendered = renderType(allocator, underlying) catch {
        allocator.free(name);
        allocator.free(c_type);
        if (comment) |text| allocator.free(text);
        return;
    };
    defer freeRenderedType(allocator, rendered);

    const main_definition = try renderAliasDefinition(allocator, name, c_type, rendered.text);
    try ctx.decls.typedefs.append(allocator, .{
        .name = name,
        .c_type = c_type,
        .main_definition = main_definition,
        .comment = comment,
        .requires_purego = rendered.requires_purego,
        .requires_unsafe = rendered.requires_unsafe,
        .requires_union_helpers = rendered.requires_union_helpers,
    });
}

fn visitorCallback(
    cursor_arg: c.CXCursor,
    _: c.CXCursor,
    client_data: c.CXClientData,
) callconv(.c) c.enum_CXChildVisitResult {
    const ctx: *VisitorContext = @ptrCast(@alignCast(client_data));
    if (ctx.failed) return c.CXChildVisit_Break;

    if (!isFromTargetHeader(cursor_arg, ctx.header_path)) {
        return c.CXChildVisit_Continue;
    }

    const kind = c.clang_getCursorKind(cursor_arg);
    switch (kind) {
        c.CXCursor_FunctionDecl => {
            collectFunction(ctx, cursor_arg) catch {
                ctx.failed = true;
                return c.CXChildVisit_Break;
            };
        },
        c.CXCursor_TypedefDecl => {
            collectTypedef(ctx, cursor_arg) catch {
                ctx.failed = true;
                return c.CXChildVisit_Break;
            };
        },
        c.CXCursor_EnumDecl => {
            collectEnumConstants(ctx, cursor_arg) catch {
                ctx.failed = true;
                return c.CXChildVisit_Break;
            };
        },
        c.CXCursor_MacroDefinition => {
            collectMacroDefinition(ctx, cursor_arg) catch {
                ctx.failed = true;
                return c.CXChildVisit_Break;
            };
        },
        c.CXCursor_VarDecl => {
            collectRuntimeVar(ctx, cursor_arg) catch {
                ctx.failed = true;
                return c.CXChildVisit_Break;
            };
        },
        else => {},
    }

    return c.CXChildVisit_Continue;
}

pub fn collectDeclarations(
    allocator: std.mem.Allocator,
    tu: *const parser.TranslationUnit,
    header_path: [:0]const u8,
) !CollectedDeclarations {
    var decls = CollectedDeclarations{ .allocator = allocator };
    errdefer decls.deinit();

    var ctx = VisitorContext{
        .decls = &decls,
        .header_path = header_path,
        .failed = false,
    };
    defer ctx.deinit(allocator);

    _ = c.clang_visitChildren(tu.cursor(), visitorCallback, @ptrCast(&ctx));

    if (ctx.failed) {
        decls.deinit();
        return error.OutOfMemory;
    }

    return decls;
}
