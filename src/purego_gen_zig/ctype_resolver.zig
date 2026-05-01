const std = @import("std");
const declarations = @import("declarations.zig");
const config_mod = @import("config.zig");

pub const CTypeMapping = struct {
    go_type: []const u8,
    comment: ?[]const u8 = null,
    owns_go_type: bool = false,
};

pub const BufferPairIndices = struct {
    pointer_index: usize,
    length_index: usize,
};

pub fn isExactExcluded(excluded_name: []const u8, name: []const u8) bool {
    return excluded_name.len != 0 and std.mem.eql(u8, excluded_name, name);
}

pub fn isIncludedOnly(included_name: []const u8, name: []const u8) bool {
    return included_name.len == 0 or std.mem.eql(u8, included_name, name);
}

pub fn isFunctionPointerCType(c_type: []const u8) bool {
    return std.mem.indexOf(u8, c_type, "(*)") != null;
}

pub fn underlyingTypedefCType(
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
) ?[]const u8 {
    for (decls.typedefs.items) |typedef_decl| {
        if (std.mem.eql(u8, typedef_decl.name, c_type)) return typedef_decl.c_type;
    }
    return null;
}

pub fn isFunctionPointerCTypeOrTypedef(
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
) bool {
    if (isFunctionPointerCType(c_type)) return true;
    if (underlyingTypedefCType(decls, c_type)) |underlying| return isFunctionPointerCType(underlying);
    return false;
}

pub fn isSupportedBufferLengthType(go_type: []const u8) bool {
    return std.mem.eql(u8, go_type, "uint64") or std.mem.eql(u8, go_type, "uint32");
}

pub fn mapCTypeToGo(c_type: []const u8) !CTypeMapping {
    if (std.mem.eql(u8, c_type, "short")) return .{ .go_type = "int16" };
    if (std.mem.eql(u8, c_type, "int")) return .{ .go_type = "int32" };
    if (std.mem.eql(u8, c_type, "int *")) return .{ .go_type = "*int32" };
    if (std.mem.eql(u8, c_type, "unsigned int")) return .{ .go_type = "uint32" };
    if (std.mem.eql(u8, c_type, "long long")) return .{ .go_type = "int64" };
    if (std.mem.eql(u8, c_type, "unsigned long long")) return .{ .go_type = "uint64" };
    if (std.mem.eql(u8, c_type, "void")) return .{ .go_type = "" };
    if (std.mem.eql(u8, c_type, "void *")) return .{ .go_type = "uintptr", .comment = "void *" };
    if (std.mem.eql(u8, c_type, "const void *")) return .{ .go_type = "uintptr", .comment = "const void *" };
    if (std.mem.eql(u8, c_type, "size_t")) return .{ .go_type = "uint64" };
    if (std.mem.eql(u8, c_type, "uint32_t")) return .{ .go_type = "uint32" };
    if (std.mem.eql(u8, c_type, "const char *")) return .{ .go_type = "string" };
    if (isFunctionPointerCType(c_type)) return .{ .go_type = "uintptr", .comment = c_type };
    if (std.mem.startsWith(u8, c_type, "struct ")) return .{ .go_type = "struct{}" };
    return error.UnsupportedCType;
}

pub fn renderPrefixedName(
    allocator: std.mem.Allocator,
    prefix: []const u8,
    name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "{s}{s}", .{ prefix, name });
}

pub fn renderTypeName(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.type_prefix, name);
}

pub fn renderConstName(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.const_prefix, name);
}

pub fn renderFuncName(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.func_prefix, name);
}

pub fn renderRuntimeVarName(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.var_prefix, name);
}

pub fn snakeToPascalCase(
    allocator: std.mem.Allocator,
    value: []const u8,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);

    var parts = std.mem.splitScalar(u8, value, '_');
    while (parts.next()) |part| {
        if (part.len == 0) continue;
        try buffer.append(allocator, std.ascii.toUpper(part[0]));
        if (part.len > 1) try buffer.appendSlice(allocator, part[1..]);
    }
    return buffer.toOwnedSlice(allocator);
}

pub fn publicApiMatcherMatches(
    name: []const u8,
    matcher: config_mod.PublicApiMatcher,
) bool {
    return switch (matcher) {
        .exact => |value| std.mem.eql(u8, name, value),
        .pattern => |value| blk: {
            if (std.mem.indexOf(u8, value, ".*")) |_| {
                const prefix = value[0..std.mem.indexOf(u8, value, ".*").?];
                const suffix = value[std.mem.indexOf(u8, value, ".*").? + 2 ..];
                if (!std.mem.startsWith(u8, name, prefix)) break :blk false;
                if (suffix.len == 0) break :blk true;
                break :blk std.mem.endsWith(u8, name, suffix);
            }
            break :blk functionNameMatchesPattern(name, value);
        },
    };
}

pub fn matchesAnyPublicApiMatcher(
    name: []const u8,
    matchers: []const config_mod.PublicApiMatcher,
) bool {
    for (matchers) |matcher| {
        if (publicApiMatcherMatches(name, matcher)) return true;
    }
    return false;
}

pub fn findPublicApiOverrideName(
    overrides: []const config_mod.PublicApiOverride,
    source_name: []const u8,
) ?[]const u8 {
    for (overrides) |override| {
        if (std.mem.eql(u8, override.source_name, source_name)) return override.public_name;
    }
    return null;
}

pub fn renderPublicApiName(
    allocator: std.mem.Allocator,
    strip_prefix: []const u8,
    overrides: []const config_mod.PublicApiOverride,
    source_name: []const u8,
) ![]u8 {
    if (findPublicApiOverrideName(overrides, source_name)) |override_name| {
        return allocator.dupe(u8, override_name);
    }

    const stripped = if (strip_prefix.len != 0 and std.mem.startsWith(u8, source_name, strip_prefix))
        source_name[strip_prefix.len..]
    else
        source_name;
    return snakeToPascalCase(allocator, stripped);
}

pub fn replaceTypeNameWithAlias(
    allocator: std.mem.Allocator,
    go_type: []const u8,
    raw_type_name: []const u8,
    public_type_name: []const u8,
) ![]u8 {
    if (std.mem.eql(u8, go_type, raw_type_name)) {
        return allocator.dupe(u8, public_type_name);
    }

    const pointer_prefix = try std.fmt.allocPrint(allocator, "*{s}", .{raw_type_name});
    defer allocator.free(pointer_prefix);
    if (std.mem.eql(u8, go_type, pointer_prefix)) {
        return std.fmt.allocPrint(allocator, "*{s}", .{public_type_name});
    }

    return allocator.dupe(u8, go_type);
}

pub fn resolveTypedefGoType(
    decls: *const declarations.CollectedDeclarations,
    typedef_decl: declarations.TypedefDecl,
    strict_enum_typedefs: bool,
) []const u8 {
    if (typedef_decl.is_enum_typedef and !strict_enum_typedefs and typedef_decl.underlying_go_type != null) {
        return typedef_decl.underlying_go_type.?;
    }
    _ = decls;
    return typedef_decl.name;
}

pub fn resolveCTypeToGo(
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
    strict_enum_typedefs: bool,
) !CTypeMapping {
    return mapCTypeToGo(c_type) catch |err| switch (err) {
        error.UnsupportedCType => {
            for (decls.typedefs.items) |typedef_decl| {
                const is_opaque_typedef =
                    std.mem.startsWith(u8, typedef_decl.c_type, "struct ") or
                    std.mem.indexOf(u8, typedef_decl.main_definition, "struct{}") != null;
                if (std.mem.eql(u8, typedef_decl.name, c_type)) {
                    if (!is_opaque_typedef and
                        !isFunctionPointerCType(typedef_decl.c_type) and
                        std.mem.indexOfScalar(u8, typedef_decl.c_type, '*') == null)
                    {
                        if (mapCTypeToGo(typedef_decl.c_type)) |underlying_mapping| {
                            return underlying_mapping;
                        } else |_| {}
                    }
                    return .{ .go_type = resolveTypedefGoType(decls, typedef_decl, strict_enum_typedefs) };
                }
                if (std.mem.eql(u8, typedef_decl.name, c_type) and is_opaque_typedef) {
                    return .{ .go_type = "struct{}" };
                }
                if (std.mem.eql(u8, c_type, typedef_decl.name)) {
                    return .{ .go_type = resolveTypedefGoType(decls, typedef_decl, strict_enum_typedefs) };
                }
                if (std.mem.eql(u8, c_type, typedef_decl.c_type)) {
                    return .{ .go_type = resolveTypedefGoType(decls, typedef_decl, strict_enum_typedefs) };
                }
                if (std.mem.endsWith(u8, c_type, " **")) {
                    const base = c_type[0 .. c_type.len - 3];
                    if (std.mem.eql(u8, base, typedef_decl.name) and is_opaque_typedef) {
                        return .{ .go_type = "uintptr", .comment = c_type };
                    }
                }
                if (std.mem.startsWith(u8, c_type, "const ") and std.mem.endsWith(u8, c_type, " **")) {
                    const base = c_type[6 .. c_type.len - 3];
                    if (std.mem.eql(u8, base, typedef_decl.name) and is_opaque_typedef) {
                        return .{ .go_type = "uintptr", .comment = c_type };
                    }
                }
                if (std.mem.endsWith(u8, c_type, " *") and !std.mem.endsWith(u8, c_type, " **")) {
                    const base = c_type[0 .. c_type.len - 2];
                    if (std.mem.eql(u8, base, typedef_decl.name) and is_opaque_typedef) {
                        return .{ .go_type = "uintptr", .comment = c_type };
                    }
                }
                if (std.mem.startsWith(u8, c_type, "const ") and std.mem.endsWith(u8, c_type, " *") and !std.mem.endsWith(u8, c_type, " **")) {
                    const base = c_type[6 .. c_type.len - 2];
                    if (std.mem.eql(u8, base, typedef_decl.name) and is_opaque_typedef) {
                        return .{ .go_type = "uintptr", .comment = c_type };
                    }
                }
            }
            return err;
        },
    };
}

pub fn resolvedGoTypeNeedsFree(c_type: []const u8, mapped: CTypeMapping) bool {
    _ = c_type;
    return mapped.owns_go_type;
}

pub fn functionNameMatchesPattern(name: []const u8, pattern: []const u8) bool {
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

pub fn containsString(items: []const []const u8, needle: []const u8) bool {
    for (items) |item| {
        if (std.mem.eql(u8, item, needle)) return true;
    }
    return false;
}

pub fn findFunctionByName(
    decls: *const declarations.CollectedDeclarations,
    name: []const u8,
) ?declarations.FunctionDecl {
    for (decls.functions.items) |func| {
        if (std.mem.eql(u8, func.name, name)) return func;
    }
    return null;
}

pub fn findParameterIndexByName(func: declarations.FunctionDecl, name: []const u8) ?usize {
    for (func.parameter_names, 0..) |param_name, index| {
        if (std.mem.eql(u8, param_name, name)) return index;
    }
    return null;
}

pub fn sortFunctionIndicesByName(indices: []usize, functions: []const declarations.FunctionDecl) void {
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
