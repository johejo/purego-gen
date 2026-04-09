const std = @import("std");
const declarations = @import("declarations.zig");
const parser = @import("parser.zig");

pub const EmitKind = enum {
    func,
    type,
    @"const",
    var_decl,
};

pub const BufferParamPair = struct {
    pointer: []const u8,
    length: []const u8,
};

pub const ExplicitBufferParamHelper = struct {
    function_name: []const u8,
    pairs: []const BufferParamPair,
};

pub const PatternBufferParamHelper = struct {
    function_pattern: []const u8,
};

pub const BufferParamHelper = union(enum) {
    explicit: ExplicitBufferParamHelper,
    pattern: PatternBufferParamHelper,
};

pub const GeneratorConfig = struct {
    lib_id: []const u8,
    package_name: []const u8,
    emit: []const EmitKind,
    struct_accessors: bool = false,
    buffer_param_helpers: []const BufferParamHelper = &.{},

    pub fn deinit(self: *const GeneratorConfig, allocator: std.mem.Allocator) void {
        allocator.free(self.lib_id);
        allocator.free(self.package_name);
        allocator.free(self.emit);
        for (self.buffer_param_helpers) |helper| {
            switch (helper) {
                .explicit => |explicit| {
                    allocator.free(explicit.function_name);
                    for (explicit.pairs) |pair| {
                        allocator.free(pair.pointer);
                        allocator.free(pair.length);
                    }
                    allocator.free(explicit.pairs);
                },
                .pattern => |pattern| {
                    allocator.free(pattern.function_pattern);
                },
            }
        }
        allocator.free(self.buffer_param_helpers);
    }
};

const CTypeMapping = struct {
    go_type: []const u8,
    comment: ?[]const u8 = null,
};

const BufferPairIndices = struct {
    pointer_index: usize,
    length_index: usize,
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
    for (src.constants.items) |constant_decl| {
        if (!hasConstantNamed(dst, constant_decl.name)) {
            try dst.constants.append(allocator, constant_decl);
            continue;
        }
        allocator.free(constant_decl.name);
        allocator.free(constant_decl.value_expr);
    }
    for (src.runtime_vars.items) |runtime_var_decl| {
        if (!hasRuntimeVarNamed(dst, runtime_var_decl.name)) {
            try dst.runtime_vars.append(allocator, runtime_var_decl);
            continue;
        }
        allocator.free(runtime_var_decl.name);
        allocator.free(runtime_var_decl.c_type);
    }
    src.functions.items.len = 0;
    src.functions.deinit(allocator);
    src.typedefs.items.len = 0;
    src.typedefs.deinit(allocator);
    src.constants.items.len = 0;
    src.constants.deinit(allocator);
    src.runtime_vars.items.len = 0;
    src.runtime_vars.deinit(allocator);
    src.functions = .{};
    src.typedefs = .{};
    src.constants = .{};
    src.runtime_vars = .{};
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
    allocator.free(typedef_decl.main_definition);
    if (typedef_decl.helper_type_definition) |text| allocator.free(text);
    if (typedef_decl.helper_function_definition) |text| allocator.free(text);
    for (typedef_decl.accessor_fields) |field| {
        allocator.free(field.name);
        allocator.free(field.go_type);
    }
    allocator.free(typedef_decl.accessor_fields);
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

fn hasConstantNamed(decls: *const declarations.CollectedDeclarations, name: []const u8) bool {
    for (decls.constants.items) |constant_decl| {
        if (std.mem.eql(u8, constant_decl.name, name)) return true;
    }
    return false;
}

fn hasRuntimeVarNamed(decls: *const declarations.CollectedDeclarations, name: []const u8) bool {
    for (decls.runtime_vars.items) |runtime_var_decl| {
        if (std.mem.eql(u8, runtime_var_decl.name, name)) return true;
    }
    return false;
}

fn mapCTypeToGo(c_type: []const u8) !CTypeMapping {
    if (std.mem.eql(u8, c_type, "int")) return .{ .go_type = "int32" };
    if (std.mem.eql(u8, c_type, "void")) return .{ .go_type = "" };
    if (std.mem.eql(u8, c_type, "void *")) return .{ .go_type = "uintptr", .comment = "void *" };
    if (std.mem.eql(u8, c_type, "const void *")) return .{ .go_type = "uintptr", .comment = "const void *" };
    if (std.mem.eql(u8, c_type, "size_t")) return .{ .go_type = "uint64" };
    if (std.mem.eql(u8, c_type, "uint32_t")) return .{ .go_type = "uint32" };
    if (std.mem.eql(u8, c_type, "const char *")) return .{ .go_type = "string" };
    if (std.mem.startsWith(u8, c_type, "struct ")) return .{ .go_type = "struct{}" };
    return error.UnsupportedCType;
}

fn isSupportedBufferLengthType(go_type: []const u8) bool {
    return std.mem.eql(u8, go_type, "uint64") or std.mem.eql(u8, go_type, "uint32");
}

fn containsString(items: []const []const u8, needle: []const u8) bool {
    for (items) |item| {
        if (std.mem.eql(u8, item, needle)) return true;
    }
    return false;
}

fn findFunctionByName(
    decls: *const declarations.CollectedDeclarations,
    name: []const u8,
) ?declarations.FunctionDecl {
    for (decls.functions.items) |func| {
        if (std.mem.eql(u8, func.name, name)) return func;
    }
    return null;
}

fn findParameterIndexByName(func: declarations.FunctionDecl, name: []const u8) ?usize {
    for (func.parameter_names, 0..) |param_name, index| {
        if (std.mem.eql(u8, param_name, name)) return index;
    }
    return null;
}

fn resolveBufferPair(
    allocator: std.mem.Allocator,
    func: declarations.FunctionDecl,
    pair: BufferParamPair,
    seen_pointer_names: *std.ArrayList([]const u8),
) !BufferPairIndices {
    const pointer_index = findParameterIndexByName(func, pair.pointer) orelse return error.BufferHelperParameterNotFound;
    const length_index = findParameterIndexByName(func, pair.length) orelse return error.BufferHelperParameterNotFound;
    const pointer_name = func.parameter_names[pointer_index];
    if (containsString(seen_pointer_names.items, pointer_name)) {
        return error.DuplicateBufferPointerParameter;
    }
    try seen_pointer_names.append(allocator, pointer_name);

    if (!std.mem.eql(u8, func.parameter_c_types[pointer_index], "const void *")) {
        return error.InvalidBufferPointerParameterType;
    }
    const pointer_go_type = try mapCTypeToGo(func.parameter_c_types[pointer_index]);
    if (!std.mem.eql(u8, pointer_go_type.go_type, "uintptr")) {
        return error.InvalidBufferPointerParameterType;
    }

    const length_go_type = try mapCTypeToGo(func.parameter_c_types[length_index]);
    if (!isSupportedBufferLengthType(length_go_type.go_type)) {
        return error.InvalidBufferLengthParameterType;
    }

    return .{
        .pointer_index = pointer_index,
        .length_index = length_index,
    };
}

fn resolveExplicitBufferPairs(
    allocator: std.mem.Allocator,
    func: declarations.FunctionDecl,
    pairs: []const BufferParamPair,
) ![]BufferPairIndices {
    var resolved: std.ArrayList(BufferPairIndices) = .empty;
    errdefer resolved.deinit(allocator);
    var seen_pointer_names: std.ArrayList([]const u8) = .empty;
    defer seen_pointer_names.deinit(allocator);

    for (pairs) |pair| {
        try resolved.append(allocator, try resolveBufferPair(allocator, func, pair, &seen_pointer_names));
    }

    return resolved.toOwnedSlice(allocator);
}

fn detectBufferPairs(
    allocator: std.mem.Allocator,
    func: declarations.FunctionDecl,
) ![]BufferPairIndices {
    var pairs: std.ArrayList(BufferPairIndices) = .empty;
    errdefer pairs.deinit(allocator);

    var index: usize = 0;
    while (index + 1 < func.parameter_c_types.len) {
        const pointer_mapping = mapCTypeToGo(func.parameter_c_types[index]) catch {
            index += 1;
            continue;
        };
        const length_mapping = mapCTypeToGo(func.parameter_c_types[index + 1]) catch {
            index += 1;
            continue;
        };

        if (std.mem.eql(u8, func.parameter_c_types[index], "const void *") and
            std.mem.eql(u8, pointer_mapping.go_type, "uintptr") and
            isSupportedBufferLengthType(length_mapping.go_type))
        {
            try pairs.append(allocator, .{
                .pointer_index = index,
                .length_index = index + 1,
            });
            index += 2;
            continue;
        }
        index += 1;
    }

    return pairs.toOwnedSlice(allocator);
}

fn sortFunctionIndicesByName(indices: []usize, functions: []const declarations.FunctionDecl) void {
    if (indices.len < 2) return;
    var i: usize = 1;
    while (i < indices.len) : (i += 1) {
        const current = indices[i];
        var j = i;
        while (j > 0 and std.mem.lessThan(u8, functions[current].name, functions[indices[j - 1]].name)) : (j -= 1) {
            indices[j] = indices[j - 1];
        }
        indices[j] = current;
    }
}

fn functionNameMatchesPattern(name: []const u8, pattern: []const u8) bool {
    var parts = std.mem.splitScalar(u8, pattern, '|');
    while (parts.next()) |raw_part| {
        var part = raw_part;
        const anchored_start = std.mem.startsWith(u8, part, "^");
        if (anchored_start) part = part[1..];
        const anchored_end = std.mem.endsWith(u8, part, "$");
        if (anchored_end) part = part[0 .. part.len - 1];

        if (anchored_start and anchored_end) {
            if (std.mem.eql(u8, name, part)) return true;
            continue;
        }
        if (anchored_start) {
            if (std.mem.startsWith(u8, name, part)) return true;
            continue;
        }
        if (anchored_end) {
            if (std.mem.endsWith(u8, name, part)) return true;
            continue;
        }
        if (std.mem.indexOf(u8, name, part) != null) return true;
    }
    return false;
}

fn containsEmitKind(items: []const EmitKind, needle: EmitKind) bool {
    for (items) |item| {
        if (item == needle) return true;
    }
    return false;
}

fn declarationsNeedPurego(decls: *const declarations.CollectedDeclarations) bool {
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.requires_purego) return true;
    }
    return false;
}

fn declarationsNeedUnsafe(decls: *const declarations.CollectedDeclarations) bool {
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.requires_unsafe or typedef_decl.requires_union_helpers) return true;
    }
    return false;
}

fn declarationsNeedFmt(
    emits_functions: bool,
    emits_runtime_vars: bool,
    decls: *const declarations.CollectedDeclarations,
) bool {
    return emits_functions or emits_runtime_vars or declarationsNeedPurego(decls);
}

fn declarationsNeedUnionHelpers(decls: *const declarations.CollectedDeclarations) bool {
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.requires_union_helpers) return true;
    }
    return false;
}

fn declarationsHaveHelperFunctions(decls: *const declarations.CollectedDeclarations) bool {
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.helper_function_definition != null) return true;
    }
    return declarationsNeedUnionHelpers(decls);
}

fn writeTypedefs(w: anytype, decls: *const declarations.CollectedDeclarations) !void {
    try w.writeAll("type (\n");
    for (decls.typedefs.items) |typedef_decl| {
        try w.writeAll(typedef_decl.main_definition);
    }
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.helper_type_definition) |helper_type_definition| try w.writeAll(helper_type_definition);
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
                const mapped = try mapCTypeToGo(param_c_type);
                if (mapped.comment) |comment| {
                    try w.print("\t\t// C: {s}\n", .{comment});
                }
                try w.print("\t\t{s} {s},\n", .{ param_name, mapped.go_type });
            }
            const result_mapped = try mapCTypeToGo(func.result_c_type);
            if (result_mapped.comment) |comment| {
                try w.print("\t\t// C: {s}\n", .{comment});
            }
            try w.writeAll("\t)");
        }

        const result_mapped = try mapCTypeToGo(func.result_c_type);
        if (result_mapped.go_type.len != 0) {
            try w.print(" {s}\n", .{result_mapped.go_type});
        } else {
            try w.writeByte('\n');
        }
    }
    try w.writeAll(")\n");
}

fn findPairByPointerIndex(pairs: []const BufferPairIndices, pointer_index: usize) ?BufferPairIndices {
    for (pairs) |pair| {
        if (pair.pointer_index == pointer_index) return pair;
    }
    return null;
}

fn findPairByLengthIndex(pairs: []const BufferPairIndices, length_index: usize) ?BufferPairIndices {
    for (pairs) |pair| {
        if (pair.length_index == length_index) return pair;
    }
    return null;
}

fn writeBufferHelper(
    w: anytype,
    func: declarations.FunctionDecl,
    pairs: []const BufferPairIndices,
) !void {
    try w.print("func {s}_bytes(\n", .{func.name});
    for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, index| {
        if (findPairByLengthIndex(pairs, index) != null) continue;
        if (findPairByPointerIndex(pairs, index) != null) {
            try w.print("\t{s} []byte,\n", .{param_name});
            continue;
        }
        const mapped = try mapCTypeToGo(param_c_type);
        if (mapped.comment) |comment| {
            try w.print("\t// C: {s}\n", .{comment});
        }
        try w.print("\t{s} {s},\n", .{ param_name, mapped.go_type });
    }

    const result_mapped = try mapCTypeToGo(func.result_c_type);
    try w.writeAll(")");
    if (result_mapped.go_type.len != 0) {
        try w.print(" {s} {{\n", .{result_mapped.go_type});
    } else {
        try w.writeAll(" {\n");
    }

    for (pairs) |pair| {
        const pointer_name = func.parameter_names[pair.pointer_index];
        try w.print("\t{s}_ptr := uintptr(0)\n", .{pointer_name});
        try w.print("\t{s}_len := {s}\n", .{ pointer_name, pointer_name });
        try w.print("\tif len({s}_len) > 0 {{\n", .{pointer_name});
        try w.print("\t\t{s}_ptr = uintptr(unsafe.Pointer(&{s}_len[0]))\n", .{ pointer_name, pointer_name });
        try w.writeAll("\t}\n");
    }

    const returns_value = result_mapped.go_type.len != 0;
    if (returns_value) {
        try w.print("\treturn {s}(\n", .{func.name});
    } else {
        try w.print("\t{s}(\n", .{func.name});
    }

    for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, index| {
        _ = param_c_type;
        if (findPairByPointerIndex(pairs, index)) |pair| {
            _ = pair;
            try w.print("\t\t{s}_ptr,\n", .{param_name});
            continue;
        }
        if (findPairByLengthIndex(pairs, index)) |pair| {
            const pointer_name = func.parameter_names[pair.pointer_index];
            const length_mapping = try mapCTypeToGo(func.parameter_c_types[pair.length_index]);
            try w.print("\t\t{s}(len({s}_len)),\n", .{ length_mapping.go_type, pointer_name });
            continue;
        }
        try w.print("\t\t{s},\n", .{param_name});
    }
    try w.writeAll("\t)\n");
    try w.writeAll("}\n");
}

fn writeBufferHelpers(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    if (config.buffer_param_helpers.len == 0) return;

    var explicit_names: std.ArrayList([]const u8) = .empty;
    defer explicit_names.deinit(allocator);
    for (config.buffer_param_helpers) |helper| {
        switch (helper) {
            .explicit => |explicit| try explicit_names.append(allocator, explicit.function_name),
            .pattern => {},
        }
    }

    var emitted_names: std.ArrayList([]const u8) = .empty;
    defer emitted_names.deinit(allocator);

    for (config.buffer_param_helpers) |helper| {
        switch (helper) {
            .explicit => |explicit| {
                const func = findFunctionByName(decls, explicit.function_name) orelse return error.BufferHelperTargetFunctionNotFound;
                const pairs = try resolveExplicitBufferPairs(allocator, func, explicit.pairs);
                defer allocator.free(pairs);
                try writeBufferHelper(w, func, pairs);
                try emitted_names.append(allocator, func.name);
            },
            .pattern => |pattern| {
                const function_count = decls.functions.items.len;
                const indices = try allocator.alloc(usize, function_count);
                defer allocator.free(indices);
                for (indices, 0..) |*slot, index| {
                    slot.* = index;
                }
                sortFunctionIndicesByName(indices, decls.functions.items);

                var match_count: usize = 0;
                for (indices) |index| {
                    const func = decls.functions.items[index];
                    if (containsString(explicit_names.items, func.name)) continue;
                    if (containsString(emitted_names.items, func.name)) continue;
                    if (!functionNameMatchesPattern(func.name, pattern.function_pattern)) continue;

                    const pairs = try detectBufferPairs(allocator, func);
                    defer allocator.free(pairs);
                    if (pairs.len == 0) continue;

                    try writeBufferHelper(w, func, pairs);
                    try emitted_names.append(allocator, func.name);
                    match_count += 1;
                }
                if (match_count == 0) return error.BufferPatternMatchedNoFunctions;
            },
        }
    }
}

fn writeStructAccessors(w: anytype, decls: *const declarations.CollectedDeclarations) !void {
    var wrote_any = false;
    for (decls.typedefs.items) |typedef_decl| {
        for (typedef_decl.accessor_fields) |field| {
            if (wrote_any) try w.writeByte('\n');
            wrote_any = true;
            try w.print("func (s *{s}) Get_{s}() {s} {{\n", .{ typedef_decl.name, field.name, field.go_type });
            try w.print("\treturn s.{s}\n", .{field.name});
            try w.writeAll("}\n\n");
            try w.print("func (s *{s}) Set_{s}(v {s}) {{\n", .{ typedef_decl.name, field.name, field.go_type });
            try w.print("\ts.{s} = v\n", .{field.name});
            try w.writeAll("}\n");
        }
    }
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

fn writeHelperFunctions(w: anytype, decls: *const declarations.CollectedDeclarations) !void {
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.helper_function_definition) |helper_function_definition| {
            try w.writeAll(helper_function_definition);
            try w.writeByte('\n');
        }
    }
    if (declarationsNeedUnionHelpers(decls)) {
        try w.writeAll("func union_get[T any, U any](u *U) T {\n");
        try w.writeAll("\treturn *(*T)(unsafe.Pointer(u))\n");
        try w.writeAll("}\n\n");
        try w.writeAll("func union_set[T any, U any](u *U, v T) {\n");
        try w.writeAll("\t*(*T)(unsafe.Pointer(u)) = v\n");
        try w.writeAll("}\n\n");
    }
}

fn writeConstants(w: anytype, decls: *const declarations.CollectedDeclarations) !void {
    if (decls.constants.items.len == 0) return;
    try w.writeAll("const (\n");
    for (decls.constants.items, 0..) |constant_decl, index| {
        if (index == 0) {
            try w.print("\t{s} = {s}\n", .{ constant_decl.name, constant_decl.value_expr });
            continue;
        }
        try w.print("\t{s}  = {s}\n", .{ constant_decl.name, constant_decl.value_expr });
    }
    try w.writeAll(")\n");
}

fn writeRuntimeVars(
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    if (decls.runtime_vars.items.len == 0) return;
    try w.writeAll("var (\n");
    for (decls.runtime_vars.items) |runtime_var_decl| {
        _ = runtime_var_decl.c_type;
        try w.print("\t{s} uintptr\n", .{runtime_var_decl.name});
    }
    try w.writeAll(")\n\n");

    try w.print("func {s}_load_runtime_vars(handle uintptr) error {{\n", .{config.lib_id});
    for (decls.runtime_vars.items) |runtime_var_decl| {
        try w.print(
            "\t{s}_symbol, err := purego.Dlsym(handle, \"{s}\")\n",
            .{ runtime_var_decl.name, runtime_var_decl.name },
        );
        try w.writeAll("\tif err != nil {\n");
        try w.print(
            "\t\treturn fmt.Errorf(\n\t\t\t\"purego-gen: failed to resolve runtime var symbol {s}: %w\",\n\t\t\terr,\n\t\t)\n",
            .{runtime_var_decl.name},
        );
        try w.writeAll("\t}\n");
        try w.print("\t{s} = {s}_symbol\n", .{ runtime_var_decl.name, runtime_var_decl.name });
    }
    try w.writeAll("\treturn nil\n");
    try w.writeAll("}\n");
}

fn formatGoSource(
    allocator: std.mem.Allocator,
    source: []const u8,
) ![]u8 {
    const temp_path = try std.fmt.allocPrint(
        allocator,
        "/tmp/purego-gen-zig-{d}.go",
        .{std.time.nanoTimestamp()},
    );
    defer allocator.free(temp_path);
    defer std.fs.deleteFileAbsolute(temp_path) catch {};

    {
        const file = try std.fs.createFileAbsolute(temp_path, .{ .truncate = true });
        defer file.close();
        try file.writeAll(source);
    }

    const result = try std.process.Child.run(.{
        .allocator = allocator,
        .argv = &.{ "gofmt", "-w", temp_path },
    });
    defer allocator.free(result.stdout);
    defer allocator.free(result.stderr);

    switch (result.term) {
        .Exited => |code| {
            if (code != 0) return error.GofmtFailed;
        },
        else => return error.GofmtFailed,
    }

    const file = try std.fs.openFileAbsolute(temp_path, .{});
    defer file.close();
    return try file.readToEndAlloc(allocator, 1024 * 1024);
}

pub fn generateGoSource(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) ![]u8 {
    const emits_functions = containsEmitKind(config.emit, .func);
    const emits_types = containsEmitKind(config.emit, .type);
    const emits_constants = containsEmitKind(config.emit, .@"const");
    const emits_runtime_vars = containsEmitKind(config.emit, .var_decl);
    const emits_struct_accessors = emits_types and config.struct_accessors;
    const has_emitted_runtime_vars = emits_runtime_vars and decls.runtime_vars.items.len > 0;

    const need_purego = emits_functions or has_emitted_runtime_vars or declarationsNeedPurego(decls);
    const need_unsafe = emits_functions or declarationsNeedUnsafe(decls);
    const need_fmt = declarationsNeedFmt(emits_functions, has_emitted_runtime_vars, decls);
    const has_helper_functions = declarationsHaveHelperFunctions(decls);

    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try w.writeAll("// Code generated by purego-gen; DO NOT EDIT.\n\n");
    try w.print("package {s}\n\n", .{config.package_name});

    if (need_fmt or need_unsafe or need_purego) {
        try w.writeAll("import (\n");
        if (need_fmt) {
            try w.writeAll("\t\"fmt\"\n");
        }
        if (need_unsafe) {
            try w.writeAll("\t\"unsafe\"\n");
        }
        if ((need_fmt and need_purego) or (need_unsafe and need_purego)) {
            try w.writeByte('\n');
        }
        if (need_purego) {
            try w.writeAll("\t\"github.com/ebitengine/purego\"\n");
        }
        try w.writeAll(")\n\n");
    }

    if (need_fmt or need_unsafe) {
        try w.writeAll("var (\n");
        if (need_fmt) {
            try w.writeAll("\t_ = fmt.Errorf\n");
        }
        if (need_unsafe) {
            try w.writeAll("\t_ = unsafe.Pointer(nil)\n");
        }
        try w.writeAll(")\n\n");
    }

    if (emits_types) {
        try writeTypedefs(w, decls);
        try w.writeByte('\n');
    }
    if (emits_constants and !has_helper_functions) {
        try writeConstants(w, decls);
        try w.writeByte('\n');
    }
    if (emits_struct_accessors) {
        try writeStructAccessors(w, decls);
        try w.writeByte('\n');
    }
    if (declarationsNeedPurego(decls) or declarationsNeedUnionHelpers(decls)) {
        try writeHelperFunctions(w, decls);
    }
    if (emits_constants and has_helper_functions) {
        try writeConstants(w, decls);
        try w.writeByte('\n');
    }
    if (emits_functions) {
        try writeFunctions(w, decls);
        try w.writeByte('\n');
        try writeBufferHelpers(allocator, w, config, decls);
        if (config.buffer_param_helpers.len > 0) {
            try w.writeByte('\n');
        }
        try writeRegisterFunctions(w, config, decls);
    }
    if (emits_runtime_vars) {
        if (emits_types or emits_struct_accessors or declarationsNeedPurego(decls) or declarationsNeedUnionHelpers(decls) or emits_functions or emits_constants) {
            try w.writeByte('\n');
        }
        try writeRuntimeVars(w, config, decls);
    }

    const rendered = try buffer.toOwnedSlice(allocator);
    defer allocator.free(rendered);
    return formatGoSource(allocator, rendered);
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
