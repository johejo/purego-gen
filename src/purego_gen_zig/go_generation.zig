const std = @import("std");
const declarations = @import("declarations.zig");
const parser = @import("parser.zig");

pub const EmitKind = enum {
    func,
    type,
    @"const",
    var_decl,
};

pub const GeneratorConfig = struct {
    lib_id: []const u8,
    package_name: []const u8,
    emit: []const EmitKind,
};

fn mergeDeclarations(
    allocator: std.mem.Allocator,
    dst: *declarations.CollectedDeclarations,
    src: *declarations.CollectedDeclarations,
) !void {
    for (src.functions.items) |func| {
        if (!hasFunctionNamed(dst, func.name)) {
            try dst.functions.append(allocator, func);
            continue;
        }
        freeFunctionDecl(allocator, func);
    }
    for (src.typedefs.items) |typedef_decl| {
        if (!hasTypedefNamed(dst, typedef_decl.name)) {
            try dst.typedefs.append(allocator, typedef_decl);
            continue;
        }
        freeTypedefDecl(allocator, typedef_decl);
    }
    src.functions.items.len = 0;
    src.functions.deinit(allocator);
    src.typedefs.items.len = 0;
    src.typedefs.deinit(allocator);
    src.functions = .{};
    src.typedefs = .{};
}

fn freeFunctionDecl(allocator: std.mem.Allocator, func: declarations.FunctionDecl) void {
    allocator.free(func.name);
    allocator.free(func.result_c_type);
    for (func.parameter_c_types) |param_c_type| allocator.free(param_c_type);
    allocator.free(func.parameter_c_types);
    for (func.parameter_names) |param_name| allocator.free(param_name);
    allocator.free(func.parameter_names);
}

fn freeTypedefDecl(allocator: std.mem.Allocator, typedef_decl: declarations.TypedefDecl) void {
    allocator.free(typedef_decl.name);
    allocator.free(typedef_decl.c_type);
}

fn hasFunctionNamed(decls: *const declarations.CollectedDeclarations, name: []const u8) bool {
    for (decls.functions.items) |func| {
        if (std.mem.eql(u8, func.name, name)) return true;
    }
    return false;
}

fn hasTypedefNamed(decls: *const declarations.CollectedDeclarations, name: []const u8) bool {
    for (decls.typedefs.items) |typedef_decl| {
        if (std.mem.eql(u8, typedef_decl.name, name)) return true;
    }
    return false;
}

fn mapCTypeToGo(c_type: []const u8) ![]const u8 {
    if (std.mem.eql(u8, c_type, "int")) return "int32";
    if (std.mem.eql(u8, c_type, "void")) return "";
    if (std.mem.eql(u8, c_type, "void *")) return "uintptr";
    if (std.mem.startsWith(u8, c_type, "struct ")) return "struct{}";
    return error.UnsupportedCType;
}

fn containsEmitKind(items: []const EmitKind, needle: EmitKind) bool {
    for (items) |item| {
        if (item == needle) return true;
    }
    return false;
}

fn writeTypedefs(w: anytype, decls: *const declarations.CollectedDeclarations) !void {
    try w.writeAll("type (\n");
    for (decls.typedefs.items) |typedef_decl| {
        const go_type = try mapCTypeToGo(typedef_decl.c_type);
        try w.print("\t// C: {s}\n", .{typedef_decl.c_type});
        if (std.mem.eql(u8, go_type, "struct{}")) {
            try w.print("\t{s} struct{{}}\n", .{typedef_decl.name});
            continue;
        }
        try w.print("\t{s} = {s}\n", .{ typedef_decl.name, go_type });
    }
    try w.writeAll(")\n");
}

fn writeFunctions(w: anytype, decls: *const declarations.CollectedDeclarations) !void {
    try w.writeAll("var (\n");
    for (decls.functions.items) |func| {
        try w.print("\t{s} func", .{func.name});
        if (func.parameter_names.len == 0) {
            try w.writeAll("()");
        } else {
            try w.writeAll("(\n");
            for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
                const go_type = try mapCTypeToGo(param_c_type);
                try w.print("\t\t{s} {s},\n", .{ param_name, go_type });
            }
            try w.writeAll("\t)");
        }

        const result_go_type = try mapCTypeToGo(func.result_c_type);
        if (result_go_type.len != 0) {
            try w.print(" {s}\n", .{result_go_type});
        } else {
            try w.writeByte('\n');
        }
    }
    try w.writeAll(")\n");
}

fn writeRegisterFunctions(
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    try w.print("func {s}_register_functions(handle uintptr) error {{\n", .{config.lib_id});
    for (decls.functions.items) |func| {
        try w.print("\t{s}_symbol, err := purego.Dlsym(handle, \"{s}\")\n", .{ func.name, func.name });
        try w.writeAll("\tif err != nil {\n");
        try w.print(
            "\t\treturn fmt.Errorf(\"purego-gen: failed to resolve function symbol {s}: %w\", err)\n",
            .{func.name},
        );
        try w.writeAll("\t}\n");
        try w.print("\tpurego.RegisterFunc(&{s}, {s}_symbol)\n", .{ func.name, func.name });
    }
    try w.writeAll("\treturn nil\n");
    try w.writeAll("}\n");
}

pub fn generateGoSource(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) ![]u8 {
    const emits_functions = containsEmitKind(config.emit, .func);
    const emits_types = containsEmitKind(config.emit, .type);

    if (containsEmitKind(config.emit, .@"const") or containsEmitKind(config.emit, .var_decl)) {
        return error.UnsupportedEmitKinds;
    }

    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try w.writeAll("// Code generated by purego-gen; DO NOT EDIT.\n\n");
    try w.print("package {s}\n\n", .{config.package_name});
    try w.writeAll("import (\n");
    if (emits_functions) {
        try w.writeAll("\t\"fmt\"\n");
        try w.writeAll("\t\"unsafe\"\n\n");
        try w.writeAll("\t\"github.com/ebitengine/purego\"\n");
    }
    try w.writeAll(")\n\n");
    if (emits_functions) {
        try w.writeAll("var (\n");
        try w.writeAll("\t_ = fmt.Errorf\n");
        try w.writeAll("\t_ = unsafe.Pointer(nil)\n");
        try w.writeAll(")\n\n");
    }
    if (emits_types) {
        try writeTypedefs(w, decls);
        try w.writeByte('\n');
    }
    if (emits_functions) {
        try writeFunctions(w, decls);
        try w.writeByte('\n');
        try writeRegisterFunctions(w, config, decls);
    }

    return buffer.toOwnedSlice(allocator);
}

pub fn collectDeclarationsFromHeader(
    allocator: std.mem.Allocator,
    header_path_z: [:0]const u8,
    clang_args_z: []const [*:0]const u8,
) !declarations.CollectedDeclarations {
    var tu = try parser.parseHeader(header_path_z, clang_args_z);
    defer tu.deinit();
    return declarations.collectDeclarations(allocator, &tu, header_path_z);
}

pub fn collectDeclarationsFromHeaders(
    allocator: std.mem.Allocator,
    header_paths_z: []const [:0]const u8,
    clang_args_z: []const [*:0]const u8,
) !declarations.CollectedDeclarations {
    var merged = declarations.CollectedDeclarations{ .allocator = allocator };
    errdefer merged.deinit();

    for (header_paths_z) |header_path_z| {
        var decls = try collectDeclarationsFromHeader(allocator, header_path_z, clang_args_z);
        errdefer decls.deinit();
        try mergeDeclarations(allocator, &merged, &decls);
        decls.deinit();
    }

    return merged;
}
