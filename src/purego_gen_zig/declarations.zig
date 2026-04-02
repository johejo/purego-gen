const std = @import("std");
const clang = @import("clang.zig");
const parser = @import("parser.zig");
const c = clang.c;

pub const FunctionDecl = struct {
    name: []const u8,
    result_c_type: []const u8,
    parameter_c_types: []const []const u8,
    parameter_names: []const []const u8,
};

pub const TypedefDecl = struct {
    name: []const u8,
    c_type: []const u8,
};

pub const CollectedDeclarations = struct {
    allocator: std.mem.Allocator,
    functions: std.ArrayListUnmanaged(FunctionDecl) = .{},
    typedefs: std.ArrayListUnmanaged(TypedefDecl) = .{},

    pub fn deinit(self: *CollectedDeclarations) void {
        for (self.functions.items) |func| {
            self.allocator.free(func.name);
            self.allocator.free(func.result_c_type);
            for (func.parameter_c_types) |pt| self.allocator.free(pt);
            self.allocator.free(func.parameter_c_types);
            for (func.parameter_names) |pn| self.allocator.free(pn);
            self.allocator.free(func.parameter_names);
        }
        self.functions.deinit(self.allocator);
        for (self.typedefs.items) |typedef_decl| {
            self.allocator.free(typedef_decl.name);
            self.allocator.free(typedef_decl.c_type);
        }
        self.typedefs.deinit(self.allocator);
    }
};

const VisitorContext = struct {
    decls: *CollectedDeclarations,
    header_path: [:0]const u8,
    failed: bool,
};

fn dupeString(allocator: std.mem.Allocator, cx_str: c.CXString) ![]const u8 {
    defer c.clang_disposeString(cx_str);
    const slice = parser.clangString(cx_str);
    return allocator.dupe(u8, slice);
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

fn collectFunction(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    const allocator = ctx.decls.allocator;

    const name = try dupeString(allocator, c.clang_getCursorSpelling(cursor_arg));
    errdefer allocator.free(name);

    const result_type = c.clang_getCursorResultType(cursor_arg);
    const result_c_type = try dupeString(allocator, c.clang_getTypeSpelling(result_type));
    errdefer allocator.free(result_c_type);

    const num_args = c.clang_Cursor_getNumArguments(cursor_arg);
    if (num_args < 0) {
        allocator.free(name);
        allocator.free(result_c_type);
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

    try ctx.decls.functions.append(allocator, .{
        .name = name,
        .result_c_type = result_c_type,
        .parameter_c_types = param_types,
        .parameter_names = param_names,
    });
}

fn collectTypedef(ctx: *VisitorContext, cursor_arg: c.CXCursor) !void {
    const allocator = ctx.decls.allocator;
    const name = try dupeString(allocator, c.clang_getCursorSpelling(cursor_arg));
    errdefer allocator.free(name);

    const underlying = c.clang_getTypedefDeclUnderlyingType(cursor_arg);
    const c_type = try dupeString(allocator, c.clang_getTypeSpelling(underlying));
    errdefer allocator.free(c_type);

    try ctx.decls.typedefs.append(allocator, .{
        .name = name,
        .c_type = c_type,
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

    _ = c.clang_visitChildren(tu.cursor(), visitorCallback, @ptrCast(&ctx));

    if (ctx.failed) {
        decls.deinit();
        return error.OutOfMemory;
    }

    return decls;
}
