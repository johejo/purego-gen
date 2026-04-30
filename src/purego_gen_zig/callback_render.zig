const std = @import("std");
const declarations = @import("declarations.zig");
const config_mod = @import("config.zig");
const ctype_resolver = @import("ctype_resolver.zig");

pub const AutoCallbackParam = struct {
    function_index: usize,
    parameter_index: usize,
};

pub fn collectAutoCallbackParams(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]AutoCallbackParam {
    var params: std.ArrayList(AutoCallbackParam) = .empty;
    errdefer params.deinit(allocator);

    for (decls.functions.items, 0..) |func, function_index| {
        for (func.parameter_c_types, 0..) |param_c_type, parameter_index| {
            if (!ctype_resolver.isFunctionPointerCType(param_c_type)) continue;
            try params.append(allocator, .{
                .function_index = function_index,
                .parameter_index = parameter_index,
            });
        }
    }

    return params.toOwnedSlice(allocator);
}

pub fn collectExplicitCallbackParams(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    helpers: []const config_mod.ExplicitCallbackParamHelper,
) ![]AutoCallbackParam {
    var params: std.ArrayList(AutoCallbackParam) = .empty;
    errdefer params.deinit(allocator);

    for (helpers) |helper| {
        const func = ctype_resolver.findFunctionByName(decls, helper.function_name) orelse return error.CallbackHelperTargetFunctionNotFound;
        const function_index = blk: {
            for (decls.functions.items, 0..) |decl_func, index| {
                if (std.mem.eql(u8, decl_func.name, func.name)) break :blk index;
            }
            return error.CallbackHelperTargetFunctionNotFound;
        };

        for (helper.params) |param_name| {
            const parameter_index = ctype_resolver.findParameterIndexByName(func, param_name) orelse return error.CallbackHelperParameterNotFound;
            if (!ctype_resolver.isFunctionPointerCType(func.parameter_c_types[parameter_index])) {
                return error.InvalidCallbackHelperParameterType;
            }
            try params.append(allocator, .{
                .function_index = function_index,
                .parameter_index = parameter_index,
            });
        }
    }

    return params.toOwnedSlice(allocator);
}

pub fn renderCallbackFuncTypeName(
    allocator: std.mem.Allocator,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "{s}_func", .{parameter_name});
}

pub fn renderQualifiedCallbackFuncTypeName(
    allocator: std.mem.Allocator,
    function_name: []const u8,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "{s}_{s}_func", .{ function_name, parameter_name });
}

pub fn renderCallbackConstructorName(
    allocator: std.mem.Allocator,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "new_{s}", .{parameter_name});
}

pub fn renderQualifiedCallbackConstructorName(
    allocator: std.mem.Allocator,
    function_name: []const u8,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "new_{s}_{s}", .{ function_name, parameter_name });
}

pub fn shouldQualifyCallbackName(
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
    target: AutoCallbackParam,
) bool {
    const target_func = decls.functions.items[target.function_index];
    const target_param_name = target_func.parameter_names[target.parameter_index];
    const target_c_type = target_func.parameter_c_types[target.parameter_index];

    for (auto_callback_params) |candidate| {
        const candidate_func = decls.functions.items[candidate.function_index];
        const candidate_param_name = candidate_func.parameter_names[candidate.parameter_index];
        if (!std.mem.eql(u8, candidate_param_name, target_param_name)) continue;

        const candidate_c_type = candidate_func.parameter_c_types[candidate.parameter_index];
        if (!std.mem.eql(u8, candidate_c_type, target_c_type)) return true;
    }

    return false;
}

pub fn renderEffectiveCallbackFuncTypeName(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
    target: AutoCallbackParam,
) ![]u8 {
    const func = decls.functions.items[target.function_index];
    const parameter_name = func.parameter_names[target.parameter_index];
    if (shouldQualifyCallbackName(decls, auto_callback_params, target)) {
        return renderQualifiedCallbackFuncTypeName(allocator, func.name, parameter_name);
    }
    return renderCallbackFuncTypeName(allocator, parameter_name);
}

pub fn renderEffectiveCallbackConstructorName(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
    target: AutoCallbackParam,
) ![]u8 {
    const func = decls.functions.items[target.function_index];
    const parameter_name = func.parameter_names[target.parameter_index];
    if (shouldQualifyCallbackName(decls, auto_callback_params, target)) {
        return renderQualifiedCallbackConstructorName(allocator, func.name, parameter_name);
    }
    return renderCallbackConstructorName(allocator, parameter_name);
}

fn resolveCallbackSignatureCTypeToGo(
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
) !ctype_resolver.CTypeMapping {
    if (std.mem.eql(u8, c_type, "const char *")) {
        return .{ .go_type = "uintptr" };
    }
    return ctype_resolver.resolveCTypeToGo(decls, c_type, false);
}

pub fn renderCallbackGoSignature(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
) ![]u8 {
    const marker_index = std.mem.indexOf(u8, c_type, "(*)") orelse return error.UnsupportedCType;
    if (marker_index + 4 > c_type.len) return error.UnsupportedCType;
    if (c_type[marker_index + 3] != '(') return error.UnsupportedCType;
    if (c_type[c_type.len - 1] != ')') return error.UnsupportedCType;

    const result_c_type = std.mem.trim(u8, c_type[0..marker_index], " ");
    const params_raw = c_type[marker_index + 4 .. c_type.len - 1];

    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    const w = &aw.writer;
    try w.writeAll("func(");

    const trimmed_params = std.mem.trim(u8, params_raw, " ");
    if (trimmed_params.len != 0 and !std.mem.eql(u8, trimmed_params, "void")) {
        var parts = std.mem.splitScalar(u8, trimmed_params, ',');
        var wrote_any = false;
        while (parts.next()) |part| {
            const param_c_type = std.mem.trim(u8, part, " ");
            const param_mapping = try resolveCallbackSignatureCTypeToGo(decls, param_c_type);
            if (wrote_any) try w.writeAll(", ");
            wrote_any = true;
            try w.print("{s}", .{param_mapping.go_type});
        }
    }
    try w.writeByte(')');

    const result_mapping = try resolveCallbackSignatureCTypeToGo(decls, result_c_type);
    if (result_mapping.go_type.len != 0) {
        try w.print(" {s}", .{result_mapping.go_type});
    }

    return aw.toOwnedSlice();
}

pub fn resolveFunctionParameterType(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
    keep_callback_pointer: bool,
    emits_types: bool,
    strict_enum_typedefs: bool,
) !ctype_resolver.CTypeMapping {
    if (ctype_resolver.isFunctionPointerCType(c_type) and !keep_callback_pointer) {
        return .{
            .go_type = try renderCallbackGoSignature(allocator, decls, c_type),
        };
    }
    if (emits_types) {
        for (decls.typedefs.items) |typedef_decl| {
            const is_opaque_typedef =
                std.mem.startsWith(u8, typedef_decl.c_type, "struct ") or
                std.mem.indexOf(u8, typedef_decl.main_definition, "struct{}") != null;
            if (!is_opaque_typedef) continue;

            if (std.mem.endsWith(u8, c_type, " **")) {
                const base = c_type[0 .. c_type.len - 3];
                if (std.mem.eql(u8, base, typedef_decl.name)) {
                    return .{ .go_type = try std.fmt.allocPrint(allocator, "**{s}", .{typedef_decl.name}) };
                }
            }
            if (std.mem.startsWith(u8, c_type, "const ") and std.mem.endsWith(u8, c_type, " **")) {
                const base = c_type[6 .. c_type.len - 3];
                if (std.mem.eql(u8, base, typedef_decl.name)) {
                    return .{ .go_type = try std.fmt.allocPrint(allocator, "**{s}", .{typedef_decl.name}) };
                }
            }
            if (std.mem.endsWith(u8, c_type, " *") and !std.mem.endsWith(u8, c_type, " **")) {
                const base = c_type[0 .. c_type.len - 2];
                if (std.mem.eql(u8, base, typedef_decl.name)) {
                    return .{ .go_type = try std.fmt.allocPrint(allocator, "*{s}", .{typedef_decl.name}) };
                }
            }
            if (std.mem.startsWith(u8, c_type, "const ") and std.mem.endsWith(u8, c_type, " *") and !std.mem.endsWith(u8, c_type, " **")) {
                const base = c_type[6 .. c_type.len - 2];
                if (std.mem.eql(u8, base, typedef_decl.name)) {
                    return .{ .go_type = try std.fmt.allocPrint(allocator, "*{s}", .{typedef_decl.name}) };
                }
            }
        }
    }
    return ctype_resolver.resolveCTypeToGo(decls, c_type, strict_enum_typedefs);
}

pub fn resolvePublicApiGoType(
    allocator: std.mem.Allocator,
    config: config_mod.GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
    emits_types: bool,
) ![]u8 {
    const mapped = try resolveFunctionParameterType(allocator, decls, c_type, false, emits_types, config.strict_enum_typedefs);
    defer if (ctype_resolver.resolvedGoTypeNeedsFree(c_type, mapped)) allocator.free(mapped.go_type);
    var current = try allocator.dupe(u8, mapped.go_type);
    errdefer allocator.free(current);

    for (decls.typedefs.items) |typedef_decl| {
        if (!ctype_resolver.matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) continue;
        const public_name = try ctype_resolver.renderPublicApiName(
            allocator,
            config.public_api.strip_prefix,
            config.public_api.type_aliases_overrides,
            typedef_decl.name,
        );
        defer allocator.free(public_name);

        const replaced = try ctype_resolver.replaceTypeNameWithAlias(allocator, current, typedef_decl.name, public_name);
        allocator.free(current);
        current = replaced;
    }

    return current;
}

pub fn hasAutoCallbackParamForFunction(
    auto_callback_params: []const AutoCallbackParam,
    function_index: usize,
) bool {
    for (auto_callback_params) |auto_callback| {
        if (auto_callback.function_index == function_index) return true;
    }
    return false;
}

pub fn isAutoCallbackParameter(
    auto_callback_params: []const AutoCallbackParam,
    function_index: usize,
    parameter_index: usize,
) bool {
    for (auto_callback_params) |auto_callback| {
        if (auto_callback.function_index == function_index and
            auto_callback.parameter_index == parameter_index)
        {
            return true;
        }
    }
    return false;
}
