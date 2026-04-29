const std = @import("std");
const clang = @import("clang.zig");
const parser = @import("parser.zig");
const macro_eval = @import("macro_eval.zig");
const type_render = @import("type_render.zig");
const c = clang.c;

pub const FunctionDecl = struct {
    name: []const u8,
    result_c_type: []const u8,
    parameter_c_types: []const []const u8,
    parameter_names: []const []const u8,
    comment: ?[]const u8 = null,

    pub fn deinit(self: FunctionDecl, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        allocator.free(self.result_c_type);
        for (self.parameter_c_types) |pt| allocator.free(pt);
        allocator.free(self.parameter_c_types);
        for (self.parameter_names) |pn| allocator.free(pn);
        allocator.free(self.parameter_names);
        if (self.comment) |comment| allocator.free(comment);
    }
};

pub const ConstantDecl = struct {
    name: []const u8,
    value_expr: []const u8,
    typed_go_type: ?[]const u8 = null,
    comment: ?[]const u8 = null,

    pub fn deinit(self: ConstantDecl, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        allocator.free(self.value_expr);
        if (self.typed_go_type) |typed_go_type| allocator.free(typed_go_type);
        if (self.comment) |comment| allocator.free(comment);
    }
};

pub const RuntimeVarDecl = struct {
    name: []const u8,
    c_type: []const u8,
    comment: ?[]const u8 = null,

    pub fn deinit(self: RuntimeVarDecl, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        allocator.free(self.c_type);
        if (self.comment) |comment| allocator.free(comment);
    }
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

    pub fn deinit(self: TypedefDecl, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        allocator.free(self.c_type);
        allocator.free(self.main_definition);
        if (self.underlying_go_type) |underlying_go_type| allocator.free(underlying_go_type);
        if (self.comment) |comment| allocator.free(comment);
        if (self.helper_type_definition) |text| allocator.free(text);
        if (self.helper_function_definition) |text| allocator.free(text);
        for (self.accessor_fields) |field| field.deinit(allocator);
        allocator.free(self.accessor_fields);
    }
};

pub const RecordFieldDecl = struct {
    name: []const u8,
    go_type: []const u8,
    is_union: bool = false,

    pub fn deinit(self: RecordFieldDecl, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        allocator.free(self.go_type);
    }
};

pub const CollectedDeclarations = struct {
    allocator: std.mem.Allocator,
    functions: std.ArrayListUnmanaged(FunctionDecl) = .empty,
    typedefs: std.ArrayListUnmanaged(TypedefDecl) = .empty,
    constants: std.ArrayListUnmanaged(ConstantDecl) = .empty,
    runtime_vars: std.ArrayListUnmanaged(RuntimeVarDecl) = .empty,

    pub fn deinit(self: *CollectedDeclarations) void {
        for (self.functions.items) |func| func.deinit(self.allocator);
        self.functions.deinit(self.allocator);
        for (self.typedefs.items) |typedef_decl| typedef_decl.deinit(self.allocator);
        self.typedefs.deinit(self.allocator);
        for (self.constants.items) |constant_decl| constant_decl.deinit(self.allocator);
        self.constants.deinit(self.allocator);
        for (self.runtime_vars.items) |runtime_var_decl| runtime_var_decl.deinit(self.allocator);
        self.runtime_vars.deinit(self.allocator);
    }
};

pub const VisitorContext = struct {
    decls: *CollectedDeclarations,
    header_path: [:0]const u8,
    known_constant_values: std.ArrayListUnmanaged(struct {
        name: []const u8,
        value: u64,
    }) = .empty,

    fn deinit(self: *VisitorContext, allocator: std.mem.Allocator) void {
        self.known_constant_values.deinit(allocator);
    }
};

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

pub fn lookupKnownConstantValue(
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

fn enumChildBody(ctx: *VisitorContext, cursor_arg: c.CXCursor) anyerror!c.enum_CXChildVisitResult {
    if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_EnumConstantDecl) return c.CXChildVisit_Continue;
    const comment = try type_render.dupeCursorRawComment(ctx.decls.allocator, cursor_arg);
    try appendConstant(
        ctx,
        parser.clangString(c.clang_getCursorSpelling(cursor_arg)),
        c.clang_getEnumConstantDeclUnsignedValue(cursor_arg),
        null,
        null,
        comment,
    );
    return c.CXChildVisit_Continue;
}

fn collectEnumConstants(
    ctx: *VisitorContext,
    enum_decl: c.CXCursor,
) !void {
    try parser.visitChildren(VisitorContext, enumChildBody, enum_decl, ctx);
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
        token_texts[i] = try type_render.dupeString(allocator, c.clang_getTokenSpelling(tu, tokens_ptr[i]));
    }

    if (try macro_eval.parseTypedSentinelMacro(ctx, token_texts[1..])) |typed_constant| {
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

    const value = try macro_eval.evaluateMacroExpression(allocator, token_texts[1..], ctx) orelse return;
    const unsigned_sentinel_go_type = try macro_eval.parseUnsignedSentinelGoType(ctx, token_texts[1..], value);
    try appendConstant(ctx, token_texts[0], value, null, unsigned_sentinel_go_type, null);
}

const AccessorContext = struct {
    allocator: std.mem.Allocator,
    is_union: bool,
    fields: std.ArrayListUnmanaged(RecordFieldDecl) = .empty,
};

fn accessorChildBody(ctx: *AccessorContext, cursor_arg: c.CXCursor) anyerror!c.enum_CXChildVisitResult {
    if (c.clang_getCursorKind(cursor_arg) != c.CXCursor_FieldDecl) return c.CXChildVisit_Continue;
    if (c.clang_Cursor_isBitField(cursor_arg) != 0) return c.CXChildVisit_Continue;

    const field_name = parser.clangString(c.clang_getCursorSpelling(cursor_arg));
    if (field_name.len == 0) return c.CXChildVisit_Continue;

    const rendered = type_render.renderType(ctx.allocator, c.clang_getCursorType(cursor_arg)) catch {
        return c.CXChildVisit_Continue;
    };
    defer type_render.freeRenderedType(ctx.allocator, rendered);
    if (std.mem.indexOfScalar(u8, rendered.text, '\n') != null) return c.CXChildVisit_Continue;

    const dup_name = try ctx.allocator.dupe(u8, field_name);
    errdefer ctx.allocator.free(dup_name);
    const dup_type = try ctx.allocator.dupe(u8, rendered.text);
    errdefer ctx.allocator.free(dup_type);
    try ctx.fields.append(ctx.allocator, .{
        .name = dup_name,
        .go_type = dup_type,
        .is_union = ctx.is_union,
    });
    return c.CXChildVisit_Continue;
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

    var ctx = AccessorContext{ .allocator = allocator, .is_union = kind == c.CXCursor_UnionDecl };
    errdefer {
        for (ctx.fields.items) |field| field.deinit(allocator);
        ctx.fields.deinit(allocator);
    }
    try parser.visitChildren(AccessorContext, accessorChildBody, decl, &ctx);
    return ctx.fields.toOwnedSlice(allocator);
}

fn collectFunction(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    const allocator = ctx.decls.allocator;

    const name = try type_render.dupeString(allocator, c.clang_getCursorSpelling(cursor_arg));
    errdefer allocator.free(name);

    const result_type = c.clang_getCursorResultType(cursor_arg);
    const result_c_type = try type_render.dupeString(allocator, c.clang_getTypeSpelling(result_type));
    errdefer allocator.free(result_c_type);
    const comment = try type_render.dupeCursorRawComment(allocator, cursor_arg);
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
        param_types[i] = try type_render.dupeString(allocator, c.clang_getTypeSpelling(arg_type));
        param_names[i] = try type_render.dupeString(allocator, c.clang_getCursorSpelling(arg_cursor));
    }
    try type_render.normalizeParameterNames(allocator, param_names);

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
        .c_type = try type_render.dupeString(allocator, c.clang_getTypeSpelling(c.clang_getCursorType(cursor_arg))),
        .comment = try type_render.dupeCursorRawComment(allocator, cursor_arg),
    });
}

fn collectTypedef(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    const allocator = ctx.decls.allocator;

    const name = try type_render.dupeString(allocator, c.clang_getCursorSpelling(cursor_arg));
    errdefer allocator.free(name);

    const underlying = c.clang_getTypedefDeclUnderlyingType(cursor_arg);
    const c_type = try type_render.dupeString(allocator, c.clang_getTypeSpelling(underlying));
    errdefer allocator.free(c_type);
    const comment = try type_render.dupeCursorRawComment(allocator, cursor_arg);
    errdefer if (comment) |text| allocator.free(text);

    const canonical = c.clang_getCanonicalType(underlying);

    if (canonical.kind == c.CXType_Enum) {
        const enum_decl = c.clang_getTypeDeclaration(canonical);
        try collectEnumConstants(ctx, enum_decl);

        const main_definition = try type_render.renderAliasDefinition(allocator, name, c_type, "int32");
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
        if (type_render.isOpaqueRecordType(canonical)) {
            const main_definition = try type_render.renderOpaqueDefinition(allocator, name, c_type);
            try ctx.decls.typedefs.append(allocator, .{
                .name = name,
                .c_type = c_type,
                .main_definition = main_definition,
                .comment = comment,
            });
            return;
        }

        const record_type = type_render.renderRecordBody(allocator, canonical, "\t\t") catch {
            allocator.free(name);
            allocator.free(c_type);
            if (comment) |text| allocator.free(text);
            return;
        };
        defer type_render.freeRenderedType(allocator, record_type);
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
            try type_render.renderCommentedTypeDefinition(allocator, name, c_type, record_type.text)
        else
            try type_render.renderStructDefinition(allocator, name, record_type.text);
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
            const main_definition = try type_render.renderAliasDefinition(allocator, name, c_type, "uintptr");
            const helper_type_name = try type_render.renderCallbackHelperTypeName(allocator, name);
            errdefer allocator.free(helper_type_name);

            const go_signature = try type_render.renderFunctionType(allocator, pointee_canonical);
            defer allocator.free(go_signature);

            const helper_type_definition = try type_render.renderCallbackHelperDefinition(
                allocator,
                helper_type_name,
                c_type,
                go_signature,
            );
            const helper_function_definition = try type_render.renderCallbackConstructor(
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

    const rendered = type_render.renderType(allocator, underlying) catch {
        allocator.free(name);
        allocator.free(c_type);
        if (comment) |text| allocator.free(text);
        return;
    };
    defer type_render.freeRenderedType(allocator, rendered);

    const main_definition = try type_render.renderAliasDefinition(allocator, name, c_type, rendered.text);
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

fn topLevelBody(ctx: *VisitorContext, cursor_arg: c.CXCursor) anyerror!c.enum_CXChildVisitResult {
    if (!isFromTargetHeader(cursor_arg, ctx.header_path)) return c.CXChildVisit_Continue;

    switch (c.clang_getCursorKind(cursor_arg)) {
        c.CXCursor_FunctionDecl => try collectFunction(ctx, cursor_arg),
        c.CXCursor_TypedefDecl => try collectTypedef(ctx, cursor_arg),
        c.CXCursor_EnumDecl => try collectEnumConstants(ctx, cursor_arg),
        c.CXCursor_MacroDefinition => try collectMacroDefinition(ctx, cursor_arg),
        c.CXCursor_VarDecl => try collectRuntimeVar(ctx, cursor_arg),
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
    };
    defer ctx.deinit(allocator);

    try parser.visitChildren(VisitorContext, topLevelBody, tu.cursor(), &ctx);

    return decls;
}
