const std = @import("std");
const builtin = @import("builtin");
const declarations = @import("declarations.zig");
const config_mod = @import("config.zig");
const ctype_resolver = @import("ctype_resolver.zig");
const callback_render = @import("callback_render.zig");

pub const TemplateRegisterFunctionView = struct {
    name: []const u8,
    symbol: []const u8,
};

pub const AutoCallbackConstructorView = struct {
    constructor_name: []const u8,
    type_name: []const u8,
};

pub const StructAccessorView = struct {
    type_name: []const u8,
    getter_name: []const u8,
    setter_name: []const u8,
    field_name: []const u8,
    go_type: []const u8,
    is_union: bool,
};

pub const PublicWrapperParamView = struct {
    name: []const u8,
    go_type: []const u8,
};

pub const PublicWrapperView = struct {
    public_name: []const u8,
    target_name: []const u8,
    params: []const PublicWrapperParamView,
    result_type: []const u8,
};

pub const OwnedStringHelperParamView = struct {
    name: []const u8,
    go_type: []const u8,
    c_comment: []const u8,
};

pub const OwnedStringHelperView = struct {
    helper_name: []const u8,
    target_name: []const u8,
    free_name: []const u8,
    gostring_name: []const u8,
    params: []const OwnedStringHelperParamView,
};

pub const AutoCallbackWrapperParamView = struct {
    name: []const u8,
    go_type: []const u8,
    is_callback: bool,
};

pub const AutoCallbackWrapperView = struct {
    wrapper_name: []const u8,
    target_name: []const u8,
    params: []const AutoCallbackWrapperParamView,
    result_type: []const u8,
};

pub const ConstantItemView = struct {
    comment: []const u8,
    name: []const u8,
    typed_prefix: []const u8,
    value_expr: []const u8,
};

pub const TemplateSectionView = struct {
    kind: []const u8,
    gap: []const u8,
    block_items: []const []const u8 = &.{},
    text_items: []const []const u8 = &.{},
    register_functions_name: []const u8 = "",
    register_function_items: []const TemplateRegisterFunctionView = &.{},
    load_runtime_vars_name: []const u8 = "",
    runtime_var_symbol_items: []const TemplateRegisterFunctionView = &.{},
    auto_callback_constructor_items: []const AutoCallbackConstructorView = &.{},
    struct_accessor_items: []const StructAccessorView = &.{},
    public_wrapper_items: []const PublicWrapperView = &.{},
    owned_string_helper_items: []const OwnedStringHelperView = &.{},
    gostring_name: []const u8 = "",
    auto_callback_wrapper_items: []const AutoCallbackWrapperView = &.{},
    const_items: []const ConstantItemView = &.{},
};

pub fn containsEmitKind(items: []const config_mod.EmitKind, needle: config_mod.EmitKind) bool {
    for (items) |item| {
        if (item == needle) return true;
    }
    return false;
}

pub fn isOwnedStringReturnTarget(
    config: config_mod.GeneratorConfig,
    function_name: []const u8,
) bool {
    for (config.owned_string_return_helpers) |helper| {
        if (std.mem.eql(u8, helper.function_name, function_name)) return true;
    }
    return false;
}

pub fn trimCommentPrefix(line: []const u8) []const u8 {
    var trimmed = std.mem.trim(u8, line, " \t\r");
    if (std.mem.startsWith(u8, trimmed, "/**")) trimmed = trimmed[3..] else if (std.mem.startsWith(u8, trimmed, "/*")) trimmed = trimmed[2..] else if (std.mem.startsWith(u8, trimmed, "///")) trimmed = trimmed[3..] else if (std.mem.startsWith(u8, trimmed, "//")) trimmed = trimmed[2..] else if (std.mem.startsWith(u8, trimmed, "*")) trimmed = trimmed[1..];

    trimmed = std.mem.trim(u8, trimmed, " \t\r");
    if (std.mem.endsWith(u8, trimmed, "*/")) {
        trimmed = std.mem.trimEnd(u8, trimmed[0 .. trimmed.len - 2], " \t\r");
    }
    return trimmed;
}

pub fn writeComment(w: anytype, indent: []const u8, raw_comment: ?[]const u8) !void {
    const comment = raw_comment orelse return;
    var lines = std.mem.splitScalar(u8, comment, '\n');
    while (lines.next()) |line| {
        const normalized = trimCommentPrefix(line);
        if (normalized.len == 0) continue;
        try w.print("{s}// {s}\n", .{ indent, normalized });
    }
}

pub fn writePrefixedTypeDefinition(
    w: anytype,
    allocator: std.mem.Allocator,
    prefix: []const u8,
    original_name: []const u8,
    definition: []const u8,
) !void {
    if (prefix.len == 0) {
        try w.writeAll(definition);
        return;
    }

    const replacement = try std.fmt.allocPrint(allocator, "\t{s}{s}", .{ prefix, original_name });
    defer allocator.free(replacement);
    const start_needle = try std.fmt.allocPrint(allocator, "\t{s}", .{original_name});
    defer allocator.free(start_needle);
    const line_needle = try std.fmt.allocPrint(allocator, "\n\t{s}", .{original_name});
    defer allocator.free(line_needle);

    if (std.mem.indexOf(u8, definition, line_needle)) |index| {
        try w.writeAll(definition[0 .. index + 1]);
        try w.writeAll(replacement);
        try w.writeAll(definition[index + line_needle.len ..]);
        return;
    }
    if (std.mem.startsWith(u8, definition, start_needle)) {
        try w.writeAll(replacement);
        try w.writeAll(definition[start_needle.len..]);
        return;
    }
    try w.writeAll(definition);
}

pub fn resolveBufferPair(
    allocator: std.mem.Allocator,
    func: declarations.FunctionDecl,
    pair: config_mod.BufferParamPair,
    seen_pointer_names: *std.ArrayList([]const u8),
) !ctype_resolver.BufferPairIndices {
    const pointer_index = ctype_resolver.findParameterIndexByName(func, pair.pointer) orelse return error.BufferHelperParameterNotFound;
    const length_index = ctype_resolver.findParameterIndexByName(func, pair.length) orelse return error.BufferHelperParameterNotFound;
    const pointer_name = func.parameter_names[pointer_index];
    if (ctype_resolver.containsString(seen_pointer_names.items, pointer_name)) {
        return error.DuplicateBufferPointerParameter;
    }
    try seen_pointer_names.append(allocator, pointer_name);

    if (!std.mem.eql(u8, func.parameter_c_types[pointer_index], "const void *")) {
        return error.InvalidBufferPointerParameterType;
    }
    const pointer_go_type = try ctype_resolver.mapCTypeToGo(func.parameter_c_types[pointer_index]);
    if (!std.mem.eql(u8, pointer_go_type.go_type, "uintptr")) {
        return error.InvalidBufferPointerParameterType;
    }

    const length_go_type = try ctype_resolver.mapCTypeToGo(func.parameter_c_types[length_index]);
    if (!ctype_resolver.isSupportedBufferLengthType(length_go_type.go_type)) {
        return error.InvalidBufferLengthParameterType;
    }

    return .{
        .pointer_index = pointer_index,
        .length_index = length_index,
    };
}

pub fn resolveExplicitBufferPairs(
    allocator: std.mem.Allocator,
    func: declarations.FunctionDecl,
    pairs: []const config_mod.BufferParamPair,
) ![]ctype_resolver.BufferPairIndices {
    var resolved: std.ArrayList(ctype_resolver.BufferPairIndices) = .empty;
    errdefer resolved.deinit(allocator);
    var seen_pointer_names: std.ArrayList([]const u8) = .empty;
    defer seen_pointer_names.deinit(allocator);

    for (pairs) |pair| {
        try resolved.append(allocator, try resolveBufferPair(allocator, func, pair, &seen_pointer_names));
    }

    return resolved.toOwnedSlice(allocator);
}

pub fn detectBufferPairs(
    allocator: std.mem.Allocator,
    func: declarations.FunctionDecl,
) ![]ctype_resolver.BufferPairIndices {
    var pairs: std.ArrayList(ctype_resolver.BufferPairIndices) = .empty;
    errdefer pairs.deinit(allocator);

    var index: usize = 0;
    while (index + 1 < func.parameter_c_types.len) {
        const pointer_mapping = ctype_resolver.mapCTypeToGo(func.parameter_c_types[index]) catch {
            index += 1;
            continue;
        };
        const length_mapping = ctype_resolver.mapCTypeToGo(func.parameter_c_types[index + 1]) catch {
            index += 1;
            continue;
        };

        if (std.mem.eql(u8, func.parameter_c_types[index], "const void *") and
            std.mem.eql(u8, pointer_mapping.go_type, "uintptr") and
            ctype_resolver.isSupportedBufferLengthType(length_mapping.go_type))
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

fn findPairByPointerIndex(pairs: []const ctype_resolver.BufferPairIndices, pointer_index: usize) ?ctype_resolver.BufferPairIndices {
    for (pairs) |pair| {
        if (pair.pointer_index == pointer_index) return pair;
    }
    return null;
}

fn findPairByLengthIndex(pairs: []const ctype_resolver.BufferPairIndices, length_index: usize) ?ctype_resolver.BufferPairIndices {
    for (pairs) |pair| {
        if (pair.length_index == length_index) return pair;
    }
    return null;
}

fn writeBufferHelper(
    allocator: std.mem.Allocator,
    w: anytype,
    config: config_mod.GeneratorConfig,
    func: declarations.FunctionDecl,
    pairs: []const ctype_resolver.BufferPairIndices,
) !void {
    const helper_name = try std.fmt.allocPrint(allocator, "{s}_bytes", .{func.name});
    defer allocator.free(helper_name);
    const emitted_helper_name = try ctype_resolver.renderFuncName(allocator, config, helper_name);
    defer allocator.free(emitted_helper_name);
    const target_name = try ctype_resolver.renderFuncName(allocator, config, func.name);
    defer allocator.free(target_name);

    try w.print("func {s}(\n", .{emitted_helper_name});
    for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, index| {
        if (findPairByLengthIndex(pairs, index) != null) continue;
        if (findPairByPointerIndex(pairs, index) != null) {
            try w.print("\t{s} []byte,\n", .{param_name});
            continue;
        }
        const mapped = try ctype_resolver.mapCTypeToGo(param_c_type);
        if (mapped.comment) |comment| {
            try w.print("\t// C: {s}\n", .{comment});
        }
        try w.print("\t{s} {s},\n", .{ param_name, mapped.go_type });
    }

    const result_mapped = try ctype_resolver.mapCTypeToGo(func.result_c_type);
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
        try w.print("\treturn {s}(\n", .{target_name});
    } else {
        try w.print("\t{s}(\n", .{target_name});
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
            const length_mapping = try ctype_resolver.mapCTypeToGo(func.parameter_c_types[pair.length_index]);
            try w.print("\t\t{s}(len({s}_len)),\n", .{ length_mapping.go_type, pointer_name });
            continue;
        }
        try w.print("\t\t{s},\n", .{param_name});
    }
    try w.writeAll("\t)\n");
    try w.writeAll("}\n");
}

pub fn renderTypeAliasItem(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    typedef_decl: declarations.TypedefDecl,
) ![]u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;

    try writeComment(w, "\t", typedef_decl.comment);
    if (config.strict_enum_typedefs and typedef_decl.is_enum_typedef and typedef_decl.underlying_go_type != null) {
        const emitted_name = try ctype_resolver.renderTypeName(allocator, config, typedef_decl.name);
        defer allocator.free(emitted_name);
        try w.print("\t// C: {s}\n", .{typedef_decl.c_type});
        try w.print("\t{s} {s}\n", .{ emitted_name, typedef_decl.underlying_go_type.? });
    } else {
        try writePrefixedTypeDefinition(
            w,
            allocator,
            config.naming.type_prefix,
            typedef_decl.name,
            typedef_decl.main_definition,
        );
    }
    return try aw.toOwnedSlice();
}

pub fn renderFunctionVarItem(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    func: declarations.FunctionDecl,
    function_index: usize,
    callback_params: []const callback_render.AutoCallbackParam,
) ![]u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;

    try writeComment(w, "\t", func.comment);
    const func_name = try ctype_resolver.renderFuncName(allocator, config, func.name);
    defer allocator.free(func_name);
    try w.print("\t{s} func", .{func_name});
    if (func.parameter_names.len == 0) {
        try w.writeAll("()");
    } else {
        try w.writeAll("(\n");
        for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
            const mapped = try callback_render.resolveFunctionParameterType(
                allocator,
                decls,
                param_c_type,
                callback_render.isAutoCallbackParameter(callback_params, function_index, parameter_index),
                containsEmitKind(config.emit, .type),
                config.strict_enum_typedefs,
            );
            defer if (ctype_resolver.resolvedGoTypeNeedsFree(param_c_type, mapped) and !callback_render.isAutoCallbackParameter(callback_params, function_index, parameter_index)) allocator.free(mapped.go_type);
            if (mapped.comment) |comment| {
                try w.print("\t\t// C: {s}\n", .{comment});
            }
            try w.print("\t\t{s} {s},\n", .{ param_name, mapped.go_type });
        }
        const result_mapped = if (isOwnedStringReturnTarget(config, func.name))
            ctype_resolver.CTypeMapping{ .go_type = "uintptr", .comment = func.result_c_type }
        else
            try callback_render.resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
        defer if (ctype_resolver.resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
        if (result_mapped.comment) |comment| {
            try w.print("\t\t// C: {s}\n", .{comment});
        }
        try w.writeAll("\t)");
    }

    const result_mapped = if (isOwnedStringReturnTarget(config, func.name))
        ctype_resolver.CTypeMapping{ .go_type = "uintptr", .comment = func.result_c_type }
    else
        try callback_render.resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
    defer if (ctype_resolver.resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
    if (result_mapped.go_type.len != 0) {
        try w.print(" {s}\n", .{result_mapped.go_type});
    } else {
        try w.writeByte('\n');
    }
    return try aw.toOwnedSlice();
}

pub fn renderAutoCallbackTypeItem(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const callback_render.AutoCallbackParam,
    auto_callback: callback_render.AutoCallbackParam,
) ![]u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;

    const func = decls.functions.items[auto_callback.function_index];
    const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(
        allocator,
        decls,
        auto_callback_params,
        auto_callback,
    );
    defer allocator.free(helper_type_name);
    const emitted_helper_type_name = try ctype_resolver.renderTypeName(allocator, config, helper_type_name);
    defer allocator.free(emitted_helper_type_name);
    const go_signature = try callback_render.renderCallbackGoSignature(
        allocator,
        decls,
        func.parameter_c_types[auto_callback.parameter_index],
    );
    defer allocator.free(go_signature);

    try w.print("\t// C: {s}\n", .{func.parameter_c_types[auto_callback.parameter_index]});
    try w.print("\t{s} = {s}\n", .{ emitted_helper_type_name, go_signature });
    return try aw.toOwnedSlice();
}

pub fn renderBufferHelperItem(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    func: declarations.FunctionDecl,
    pairs: []const ctype_resolver.BufferPairIndices,
) ![]u8 {
    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    try writeBufferHelper(allocator, &aw.writer, config, func, pairs);
    return try aw.toOwnedSlice();
}

pub fn sectionGap(has_emitted_section: bool, add_leading_gap: bool) []const u8 {
    return if (add_leading_gap or !has_emitted_section) "\n\n" else "\n";
}

pub fn appendSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    view: TemplateSectionView,
) !void {
    try sections.append(allocator, view);
    has_emitted_section.* = true;
}

pub fn formatGoSource(
    allocator: std.mem.Allocator,
    source: []const u8,
) ![]u8 {
    var threaded_io = std.Io.Threaded.init(allocator, .{
        .environ = currentEnviron(),
    });
    defer threaded_io.deinit();
    const io = threaded_io.io();
    const temp_path = try std.fmt.allocPrint(
        allocator,
        "/tmp/purego-gen-zig-{d}.go",
        .{std.Io.Timestamp.now(io, .real).nanoseconds},
    );
    defer allocator.free(temp_path);
    defer std.Io.Dir.deleteFileAbsolute(io, temp_path) catch {};

    {
        const file = try std.Io.Dir.createFileAbsolute(io, temp_path, .{ .truncate = true });
        defer file.close(io);
        try file.writeStreamingAll(io, source);
    }

    const result = try std.process.run(allocator, io, .{
        .argv = &.{ "gofmt", "-w", temp_path },
    });
    defer allocator.free(result.stdout);
    defer allocator.free(result.stderr);

    switch (result.term) {
        .exited => |code| {
            if (code != 0) return error.GofmtFailed;
        },
        else => return error.GofmtFailed,
    }

    return try std.Io.Dir.cwd().readFileAlloc(io, temp_path, allocator, .limited(1024 * 1024));
}

fn currentEnviron() std.process.Environ {
    switch (builtin.os.tag) {
        .windows => return .{ .block = .global },
        .wasi, .emscripten => {
            if (!builtin.link_libc) return .empty;
            const c_environ = std.c.environ;
            var env_count: usize = 0;
            while (c_environ[env_count] != null) : (env_count += 1) {}
            return .{ .block = .{ .slice = @ptrCast(c_environ[0..env_count :null]) } };
        },
        .freestanding, .other => return .empty,
        else => {
            const c_environ = std.c.environ;
            var env_count: usize = 0;
            while (c_environ[env_count] != null) : (env_count += 1) {}
            return .{ .block = .{ .slice = @ptrCast(c_environ[0..env_count :null]) } };
        },
    }
}
