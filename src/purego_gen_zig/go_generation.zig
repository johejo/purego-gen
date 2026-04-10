const std = @import("std");
const declarations = @import("declarations.zig");
const gotmpl = @import("gotmpl.zig");
const parser = @import("parser.zig");

const go_file_template = @embedFile("purego_gen.gotmpl");

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

pub const ExplicitCallbackParamHelper = struct {
    function_name: []const u8,
    params: []const []const u8,
};

pub const OwnedStringReturnHelper = struct {
    function_name: []const u8,
    free_func_name: []const u8,
};

pub const PublicApiMatcher = union(enum) {
    exact: []const u8,
    pattern: []const u8,
};

pub const PublicApiOverride = struct {
    source_name: []const u8,
    public_name: []const u8,
};

pub const PublicApiConfig = struct {
    strip_prefix: []const u8,
    type_aliases_include: []const PublicApiMatcher,
    type_aliases_overrides: []const PublicApiOverride,
    wrappers_include: []const PublicApiMatcher,
    wrappers_exclude: []const PublicApiMatcher,
    wrappers_overrides: []const PublicApiOverride,
};

pub const NamingConfig = struct {
    type_prefix: []const u8,
    const_prefix: []const u8,
    func_prefix: []const u8,
    var_prefix: []const u8,
};

pub const ExcludeConfig = struct {
    func_name: []const u8,
    type_name: []const u8,
    const_name: []const u8,
    var_name: []const u8,
};

pub const IncludeConfig = struct {
    func_name: []const u8,
    type_name: []const u8,
    const_name: []const u8,
    var_name: []const u8,
};

pub const GeneratorConfig = struct {
    lib_id: []const u8,
    package_name: []const u8,
    emit: []const EmitKind,
    naming: NamingConfig,
    include: IncludeConfig,
    exclude: ExcludeConfig,
    typed_sentinel_constants: bool = false,
    strict_enum_typedefs: bool = false,
    struct_accessors: bool = false,
    buffer_param_helpers: []const BufferParamHelper = &.{},
    callback_param_helpers: []const ExplicitCallbackParamHelper = &.{},
    owned_string_return_helpers: []const OwnedStringReturnHelper = &.{},
    public_api: PublicApiConfig,
    auto_callbacks: bool = false,

    pub fn deinit(self: *const GeneratorConfig, allocator: std.mem.Allocator) void {
        allocator.free(self.lib_id);
        allocator.free(self.package_name);
        allocator.free(self.emit);
        allocator.free(self.naming.type_prefix);
        allocator.free(self.naming.const_prefix);
        allocator.free(self.naming.func_prefix);
        allocator.free(self.naming.var_prefix);
        allocator.free(self.include.func_name);
        allocator.free(self.include.type_name);
        allocator.free(self.include.const_name);
        allocator.free(self.include.var_name);
        allocator.free(self.exclude.func_name);
        allocator.free(self.exclude.type_name);
        allocator.free(self.exclude.const_name);
        allocator.free(self.exclude.var_name);
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
        for (self.callback_param_helpers) |helper| {
            allocator.free(helper.function_name);
            for (helper.params) |param| allocator.free(param);
            allocator.free(helper.params);
        }
        allocator.free(self.callback_param_helpers);
        for (self.owned_string_return_helpers) |helper| {
            allocator.free(helper.function_name);
            allocator.free(helper.free_func_name);
        }
        allocator.free(self.owned_string_return_helpers);
        allocator.free(self.public_api.strip_prefix);
        for (self.public_api.type_aliases_include) |matcher| {
            switch (matcher) {
                .exact => |value| allocator.free(value),
                .pattern => |value| allocator.free(value),
            }
        }
        allocator.free(self.public_api.type_aliases_include);
        for (self.public_api.type_aliases_overrides) |override| {
            allocator.free(override.source_name);
            allocator.free(override.public_name);
        }
        allocator.free(self.public_api.type_aliases_overrides);
        for (self.public_api.wrappers_include) |matcher| {
            switch (matcher) {
                .exact => |value| allocator.free(value),
                .pattern => |value| allocator.free(value),
            }
        }
        allocator.free(self.public_api.wrappers_include);
        for (self.public_api.wrappers_exclude) |matcher| {
            switch (matcher) {
                .exact => |value| allocator.free(value),
                .pattern => |value| allocator.free(value),
            }
        }
        allocator.free(self.public_api.wrappers_exclude);
        for (self.public_api.wrappers_overrides) |override| {
            allocator.free(override.source_name);
            allocator.free(override.public_name);
        }
        allocator.free(self.public_api.wrappers_overrides);
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

const AutoCallbackParam = struct {
    function_index: usize,
    parameter_index: usize,
};

const TemplateParamView = struct {
    name: []const u8,
    type: []const u8,
    has_c_type_comment: bool = false,
    c_type_comment: []const u8 = "",
};

const TemplateTypeAliasView = struct {
    comment_lines: []const []const u8,
    has_c_type_comment: bool,
    c_type_comment: []const u8,
    definition: []const u8,
    has_helper_type_definition: bool,
    helper_type_definition: []const u8,
};

const TemplatePublicTypeAliasView = struct {
    public_name: []const u8,
    internal_name: []const u8,
};

const TemplateAutoCallbackTypeView = struct {
    c_type_comment: []const u8,
    name: []const u8,
    go_signature: []const u8,
};

const TemplateAutoCallbackConstructorView = struct {
    name: []const u8,
    param_type: []const u8,
};

const TemplateConstantView = struct {
    comment_lines: []const []const u8,
    name: []const u8,
    has_const_type: bool,
    const_type: []const u8,
    expression: []const u8,
};

const TemplateStructAccessorView = struct {
    receiver_type: []const u8,
    getter_name: []const u8,
    setter_name: []const u8,
    go_type: []const u8,
    field_name: []const u8,
};

const TemplateHelperTextView = struct {
    text: []const u8,
};

const TemplatePublicWrapperView = struct {
    public_name: []const u8,
    parameters: []const TemplateParamView,
    has_result_type: bool,
    result_type: []const u8,
    internal_func_name: []const u8,
};

const TemplateFunctionView = struct {
    comment_lines: []const []const u8,
    name: []const u8,
    parameters: []const TemplateParamView,
    has_result_type: bool,
    result_type: []const u8,
    has_result_c_type_comment: bool,
    result_c_type_comment: []const u8,
};

const TemplateBufferHelperView = struct {
    name: []const u8,
    parameters: []const TemplateParamView,
    has_result_type: bool,
    result_type: []const u8,
    pointer_names: []const []const u8,
    target_name: []const u8,
    call_arguments: []const []const u8,
};

const TemplateAutoCallbackWrapperView = struct {
    name: []const u8,
    parameters: []const TemplateParamView,
    has_result_type: bool,
    result_type: []const u8,
    callback_parameters: []const []const u8,
    target_name: []const u8,
    call_arguments: []const []const u8,
};

const TemplateOwnedStringHelperView = struct {
    name: []const u8,
    parameters: []const TemplateParamView,
    target_name: []const u8,
    call_arguments: []const []const u8,
    free_func_name: []const u8,
};

const TemplateRegisterFunctionView = struct {
    name: []const u8,
    symbol: []const u8,
};

const AutoCallbackConstructorView = struct {
    constructor_name: []const u8,
    type_name: []const u8,
};

const StructAccessorView = struct {
    type_name: []const u8,
    getter_name: []const u8,
    setter_name: []const u8,
    field_name: []const u8,
    go_type: []const u8,
};

const PublicWrapperParamView = struct {
    name: []const u8,
    go_type: []const u8,
};

const PublicWrapperView = struct {
    public_name: []const u8,
    target_name: []const u8,
    params: []const PublicWrapperParamView,
    result_type: []const u8,
};

const OwnedStringHelperParamView = struct {
    name: []const u8,
    go_type: []const u8,
    c_comment: []const u8,
};

const OwnedStringHelperView = struct {
    helper_name: []const u8,
    target_name: []const u8,
    free_name: []const u8,
    gostring_name: []const u8,
    params: []const OwnedStringHelperParamView,
};

const AutoCallbackWrapperParamView = struct {
    name: []const u8,
    go_type: []const u8,
    is_callback: bool,
};

const AutoCallbackWrapperView = struct {
    wrapper_name: []const u8,
    target_name: []const u8,
    params: []const AutoCallbackWrapperParamView,
    result_type: []const u8,
};

const ConstantItemView = struct {
    comment: []const u8,
    name: []const u8,
    typed_prefix: []const u8,
    value_expr: []const u8,
};

const TemplateSectionView = struct {
    kind: []const u8,
    leading_gap: bool,
    block_items: []const []const u8,
    text_items: []const []const u8,
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

const TemplateRuntimeVarView = struct {
    comment_lines: []const []const u8,
    name: []const u8,
    symbol: []const u8,
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
        if (constant_decl.typed_go_type) |typed_go_type| allocator.free(typed_go_type);
        if (constant_decl.comment) |comment| allocator.free(comment);
    }
    for (src.runtime_vars.items) |runtime_var_decl| {
        if (!hasRuntimeVarNamed(dst, runtime_var_decl.name)) {
            try dst.runtime_vars.append(allocator, runtime_var_decl);
            continue;
        }
        allocator.free(runtime_var_decl.name);
        allocator.free(runtime_var_decl.c_type);
        if (runtime_var_decl.comment) |comment| allocator.free(comment);
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
    if (func.comment) |comment| allocator.free(comment);
}

fn freeTypedefDecl(allocator: std.mem.Allocator, typedef_decl: declarations.TypedefDecl) void {
    allocator.free(typedef_decl.name);
    allocator.free(typedef_decl.c_type);
    allocator.free(typedef_decl.main_definition);
    if (typedef_decl.underlying_go_type) |underlying_go_type| allocator.free(underlying_go_type);
    if (typedef_decl.comment) |comment| allocator.free(comment);
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

fn isExactExcluded(excluded_name: []const u8, name: []const u8) bool {
    return excluded_name.len != 0 and std.mem.eql(u8, excluded_name, name);
}

fn isIncludedOnly(included_name: []const u8, name: []const u8) bool {
    return included_name.len == 0 or std.mem.eql(u8, included_name, name);
}

fn mapCTypeToGo(c_type: []const u8) !CTypeMapping {
    if (std.mem.eql(u8, c_type, "int")) return .{ .go_type = "int32" };
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

fn renderPrefixedName(
    allocator: std.mem.Allocator,
    prefix: []const u8,
    name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "{s}{s}", .{ prefix, name });
}

fn renderTypeName(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.type_prefix, name);
}

fn renderConstName(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.const_prefix, name);
}

fn renderFuncName(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.func_prefix, name);
}

fn renderRuntimeVarName(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    name: []const u8,
) ![]u8 {
    return renderPrefixedName(allocator, config.naming.var_prefix, name);
}

fn isOwnedStringReturnTarget(
    config: GeneratorConfig,
    function_name: []const u8,
) bool {
    for (config.owned_string_return_helpers) |helper| {
        if (std.mem.eql(u8, helper.function_name, function_name)) return true;
    }
    return false;
}

fn snakeToPascalCase(
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

fn publicApiMatcherMatches(
    name: []const u8,
    matcher: PublicApiMatcher,
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

fn matchesAnyPublicApiMatcher(
    name: []const u8,
    matchers: []const PublicApiMatcher,
) bool {
    for (matchers) |matcher| {
        if (publicApiMatcherMatches(name, matcher)) return true;
    }
    return false;
}

fn findPublicApiOverrideName(
    overrides: []const PublicApiOverride,
    source_name: []const u8,
) ?[]const u8 {
    for (overrides) |override| {
        if (std.mem.eql(u8, override.source_name, source_name)) return override.public_name;
    }
    return null;
}

fn renderPublicApiName(
    allocator: std.mem.Allocator,
    strip_prefix: []const u8,
    overrides: []const PublicApiOverride,
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

fn replaceTypeNameWithAlias(
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

fn resolveTypedefGoType(
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

fn resolvePublicApiGoType(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
    emits_types: bool,
) ![]u8 {
    const mapped = try resolveFunctionParameterType(allocator, decls, c_type, false, emits_types, config.strict_enum_typedefs);
    defer if (resolvedGoTypeNeedsFree(c_type, mapped)) allocator.free(mapped.go_type);
    var current = try allocator.dupe(u8, mapped.go_type);
    errdefer allocator.free(current);

    for (decls.typedefs.items) |typedef_decl| {
        if (!matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) continue;
        const public_name = try renderPublicApiName(
            allocator,
            config.public_api.strip_prefix,
            config.public_api.type_aliases_overrides,
            typedef_decl.name,
        );
        defer allocator.free(public_name);

        const replaced = try replaceTypeNameWithAlias(allocator, current, typedef_decl.name, public_name);
        allocator.free(current);
        current = replaced;
    }

    return current;
}

fn writePrefixedTypeDefinition(
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

fn isFunctionPointerCType(c_type: []const u8) bool {
    return std.mem.indexOf(u8, c_type, "(*)") != null;
}

fn resolveCallbackSignatureCTypeToGo(
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
) !CTypeMapping {
    if (std.mem.eql(u8, c_type, "const char *")) {
        return .{ .go_type = "uintptr" };
    }
    return resolveCTypeToGo(decls, c_type, false);
}

fn resolveCTypeToGo(
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
                if (std.mem.endsWith(u8, c_type, " *")) {
                    const base = c_type[0 .. c_type.len - 2];
                    if (std.mem.eql(u8, base, typedef_decl.name) and is_opaque_typedef) {
                        return .{ .go_type = "uintptr", .comment = c_type };
                    }
                }
                if (std.mem.startsWith(u8, c_type, "const ") and std.mem.endsWith(u8, c_type, " *")) {
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

fn resolveFunctionParameterType(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    c_type: []const u8,
    keep_callback_pointer: bool,
    emits_types: bool,
    strict_enum_typedefs: bool,
) !CTypeMapping {
    if (isFunctionPointerCType(c_type) and !keep_callback_pointer) {
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

            if (std.mem.endsWith(u8, c_type, " *")) {
                const base = c_type[0 .. c_type.len - 2];
                if (std.mem.eql(u8, base, typedef_decl.name)) {
                    return .{ .go_type = try std.fmt.allocPrint(allocator, "*{s}", .{typedef_decl.name}) };
                }
            }
            if (std.mem.startsWith(u8, c_type, "const ") and std.mem.endsWith(u8, c_type, " *")) {
                const base = c_type[6 .. c_type.len - 2];
                if (std.mem.eql(u8, base, typedef_decl.name)) {
                    return .{ .go_type = try std.fmt.allocPrint(allocator, "*{s}", .{typedef_decl.name}) };
                }
            }
        }
    }
    return resolveCTypeToGo(decls, c_type, strict_enum_typedefs);
}

fn resolvedGoTypeNeedsFree(c_type: []const u8, mapped: CTypeMapping) bool {
    return isFunctionPointerCType(c_type) or std.mem.startsWith(u8, mapped.go_type, "*");
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

fn collectAutoCallbackParams(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]AutoCallbackParam {
    var params: std.ArrayList(AutoCallbackParam) = .empty;
    errdefer params.deinit(allocator);

    for (decls.functions.items, 0..) |func, function_index| {
        for (func.parameter_c_types, 0..) |param_c_type, parameter_index| {
            if (!isFunctionPointerCType(param_c_type)) continue;
            try params.append(allocator, .{
                .function_index = function_index,
                .parameter_index = parameter_index,
            });
        }
    }

    return params.toOwnedSlice(allocator);
}

fn collectExplicitCallbackParams(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
    helpers: []const ExplicitCallbackParamHelper,
) ![]AutoCallbackParam {
    var params: std.ArrayList(AutoCallbackParam) = .empty;
    errdefer params.deinit(allocator);

    for (helpers) |helper| {
        const func = findFunctionByName(decls, helper.function_name) orelse return error.CallbackHelperTargetFunctionNotFound;
        const function_index = blk: {
            for (decls.functions.items, 0..) |decl_func, index| {
                if (std.mem.eql(u8, decl_func.name, func.name)) break :blk index;
            }
            return error.CallbackHelperTargetFunctionNotFound;
        };

        for (helper.params) |param_name| {
            const parameter_index = findParameterIndexByName(func, param_name) orelse return error.CallbackHelperParameterNotFound;
            if (!isFunctionPointerCType(func.parameter_c_types[parameter_index])) {
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

fn containsAutoCallbackParamName(
    items: []const []const u8,
    needle: []const u8,
) bool {
    return containsString(items, needle);
}

fn renderCallbackFuncTypeName(
    allocator: std.mem.Allocator,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "{s}_func", .{parameter_name});
}

fn renderQualifiedCallbackFuncTypeName(
    allocator: std.mem.Allocator,
    function_name: []const u8,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "{s}_{s}_func", .{ function_name, parameter_name });
}

fn renderCallbackConstructorName(
    allocator: std.mem.Allocator,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "new_{s}", .{parameter_name});
}

fn renderQualifiedCallbackConstructorName(
    allocator: std.mem.Allocator,
    function_name: []const u8,
    parameter_name: []const u8,
) ![]u8 {
    return std.fmt.allocPrint(allocator, "new_{s}_{s}", .{ function_name, parameter_name });
}

fn shouldQualifyCallbackName(
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

fn renderEffectiveCallbackFuncTypeName(
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

fn renderEffectiveCallbackConstructorName(
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

fn renderCallbackGoSignature(
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

    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);
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

    return buffer.toOwnedSlice(allocator);
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

fn trimCommentPrefix(line: []const u8) []const u8 {
    var trimmed = std.mem.trim(u8, line, " \t\r");
    if (std.mem.startsWith(u8, trimmed, "/**")) trimmed = trimmed[3..] else if (std.mem.startsWith(u8, trimmed, "/*")) trimmed = trimmed[2..] else if (std.mem.startsWith(u8, trimmed, "///")) trimmed = trimmed[3..] else if (std.mem.startsWith(u8, trimmed, "//")) trimmed = trimmed[2..] else if (std.mem.startsWith(u8, trimmed, "*")) trimmed = trimmed[1..];

    trimmed = std.mem.trim(u8, trimmed, " \t\r");
    if (std.mem.endsWith(u8, trimmed, "*/")) {
        trimmed = std.mem.trimRight(u8, trimmed[0 .. trimmed.len - 2], " \t\r");
    }
    return trimmed;
}

fn writeComment(w: anytype, indent: []const u8, raw_comment: ?[]const u8) !void {
    const comment = raw_comment orelse return;
    var lines = std.mem.splitScalar(u8, comment, '\n');
    while (lines.next()) |line| {
        const normalized = trimCommentPrefix(line);
        if (normalized.len == 0) continue;
        try w.print("{s}// {s}\n", .{ indent, normalized });
    }
}

fn writeTypedefs(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    if (decls.typedefs.items.len == 0) return;
    try w.writeAll("type (\n");
    for (decls.typedefs.items) |typedef_decl| {
        try writeComment(w, "\t", typedef_decl.comment);
        if (config.strict_enum_typedefs and typedef_decl.is_enum_typedef and typedef_decl.underlying_go_type != null) {
            const emitted_name = try renderTypeName(allocator, config, typedef_decl.name);
            defer allocator.free(emitted_name);
            try w.print("\t// C: {s}\n", .{typedef_decl.c_type});
            try w.print("\t{s} {s}\n", .{ emitted_name, typedef_decl.underlying_go_type.? });
            continue;
        }
        try writePrefixedTypeDefinition(
            w,
            allocator,
            config.naming.type_prefix,
            typedef_decl.name,
            typedef_decl.main_definition,
        );
    }
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.helper_type_definition) |helper_type_definition| try w.writeAll(helper_type_definition);
    }
    try w.writeAll(")\n");
}

fn writePublicTypeAliases(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    var count: usize = 0;
    for (decls.typedefs.items) |typedef_decl| {
        if (matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) {
            count += 1;
        }
    }
    if (count == 0) return;

    try w.writeAll("type (\n");
    for (decls.typedefs.items) |typedef_decl| {
        if (!matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) continue;
        const public_name = try renderPublicApiName(
            allocator,
            config.public_api.strip_prefix,
            config.public_api.type_aliases_overrides,
            typedef_decl.name,
        );
        defer allocator.free(public_name);
        const emitted_internal_name = try renderTypeName(allocator, config, typedef_decl.name);
        defer allocator.free(emitted_internal_name);
        try w.print("\t{s} = {s}\n", .{ public_name, emitted_internal_name });
    }
    try w.writeAll(")\n");
}

fn hasPublicTypeAliases(
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) bool {
    for (decls.typedefs.items) |typedef_decl| {
        if (matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) return true;
    }
    return false;
}

fn writeFunctions(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    callback_params: []const AutoCallbackParam,
) !void {
    try w.writeAll("var (\n");
    for (decls.functions.items, 0..) |func, function_index| {
        try writeComment(w, "\t", func.comment);
        const func_name = try renderFuncName(allocator, config, func.name);
        defer allocator.free(func_name);
        try w.print("\t{s} func", .{func_name});
        if (func.parameter_names.len == 0) {
            try w.writeAll("()");
        } else {
            try w.writeAll("(\n");
            for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
                const mapped = try resolveFunctionParameterType(
                    allocator,
                    decls,
                    param_c_type,
                    isAutoCallbackParameter(callback_params, function_index, parameter_index),
                    containsEmitKind(config.emit, .type),
                    config.strict_enum_typedefs,
                );
                defer if (resolvedGoTypeNeedsFree(param_c_type, mapped) and !isAutoCallbackParameter(callback_params, function_index, parameter_index)) allocator.free(mapped.go_type);
                if (mapped.comment) |comment| {
                    try w.print("\t\t// C: {s}\n", .{comment});
                }
                try w.print("\t\t{s} {s},\n", .{ param_name, mapped.go_type });
            }
            const result_mapped = if (isOwnedStringReturnTarget(config, func.name))
                CTypeMapping{ .go_type = "uintptr", .comment = func.result_c_type }
            else
                try resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
            defer if (resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
            if (result_mapped.comment) |comment| {
                try w.print("\t\t// C: {s}\n", .{comment});
            }
            try w.writeAll("\t)");
        }

        const result_mapped = if (isOwnedStringReturnTarget(config, func.name))
            CTypeMapping{ .go_type = "uintptr", .comment = func.result_c_type }
        else
            try resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
        defer if (resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
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
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    func: declarations.FunctionDecl,
    pairs: []const BufferPairIndices,
) !void {
    const helper_name = try std.fmt.allocPrint(allocator, "{s}_bytes", .{func.name});
    defer allocator.free(helper_name);
    const emitted_helper_name = try renderFuncName(allocator, config, helper_name);
    defer allocator.free(emitted_helper_name);
    const target_name = try renderFuncName(allocator, config, func.name);
    defer allocator.free(target_name);

    try w.print("func {s}(\n", .{emitted_helper_name});
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
                try writeBufferHelper(allocator, w, config, func, pairs);
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

                    try writeBufferHelper(allocator, w, config, func, pairs);
                    try emitted_names.append(allocator, func.name);
                    match_count += 1;
                }
                if (match_count == 0) return error.BufferPatternMatchedNoFunctions;
            },
        }
    }
}

fn writeAutoCallbackTypes(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
) !void {
    if (auto_callback_params.len == 0) return;

    var emitted_names: std.ArrayList([]const u8) = .empty;
    defer {
        for (emitted_names.items) |name| allocator.free(name);
        emitted_names.deinit(allocator);
    }

    try w.writeAll("type (\n");
    for (auto_callback_params) |auto_callback| {
        const func = decls.functions.items[auto_callback.function_index];
        const helper_type_name = try renderEffectiveCallbackFuncTypeName(
            allocator,
            decls,
            auto_callback_params,
            auto_callback,
        );
        defer allocator.free(helper_type_name);
        const emitted_helper_type_name = try renderTypeName(allocator, config, helper_type_name);
        defer allocator.free(emitted_helper_type_name);
        if (containsAutoCallbackParamName(emitted_names.items, emitted_helper_type_name)) continue;
        const go_signature = try renderCallbackGoSignature(
            allocator,
            decls,
            func.parameter_c_types[auto_callback.parameter_index],
        );
        defer allocator.free(go_signature);

        try w.print("\t// C: {s}\n", .{func.parameter_c_types[auto_callback.parameter_index]});
        try w.print("\t{s} = {s}\n", .{ emitted_helper_type_name, go_signature });
        try emitted_names.append(allocator, try allocator.dupe(u8, emitted_helper_type_name));
    }
    try w.writeAll(")\n");
}

fn writeAutoCallbackConstructors(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
) !void {
    if (auto_callback_params.len == 0) return;

    var emitted_names: std.ArrayList([]const u8) = .empty;
    defer {
        for (emitted_names.items) |name| allocator.free(name);
        emitted_names.deinit(allocator);
    }

    for (auto_callback_params) |auto_callback| {
        const helper_type_name = try renderEffectiveCallbackFuncTypeName(
            allocator,
            decls,
            auto_callback_params,
            auto_callback,
        );
        defer allocator.free(helper_type_name);
        const emitted_helper_type_name = try renderTypeName(allocator, config, helper_type_name);
        defer allocator.free(emitted_helper_type_name);
        const constructor_name = try renderEffectiveCallbackConstructorName(
            allocator,
            decls,
            auto_callback_params,
            auto_callback,
        );
        defer allocator.free(constructor_name);
        const emitted_constructor_name = try renderFuncName(allocator, config, constructor_name);
        defer allocator.free(emitted_constructor_name);
        if (containsAutoCallbackParamName(emitted_names.items, emitted_constructor_name)) continue;
        try w.print(
            "func {s}(fn {s}) uintptr {{\n\treturn uintptr(purego.NewCallback(fn))\n}}\n\n",
            .{ emitted_constructor_name, emitted_helper_type_name },
        );
        try emitted_names.append(allocator, try allocator.dupe(u8, emitted_constructor_name));
    }
}

fn hasAutoCallbackParamForFunction(
    auto_callback_params: []const AutoCallbackParam,
    function_index: usize,
) bool {
    for (auto_callback_params) |auto_callback| {
        if (auto_callback.function_index == function_index) return true;
    }
    return false;
}

fn isAutoCallbackParameter(
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

fn writeAutoCallbackWrappers(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
) !void {
    if (auto_callback_params.len == 0) return;

    for (decls.functions.items, 0..) |func, function_index| {
        if (!hasAutoCallbackParamForFunction(auto_callback_params, function_index)) continue;

        const wrapper_name = try std.fmt.allocPrint(allocator, "{s}_callbacks", .{func.name});
        defer allocator.free(wrapper_name);
        const emitted_wrapper_name = try renderFuncName(allocator, config, wrapper_name);
        defer allocator.free(emitted_wrapper_name);
        const target_name = try renderFuncName(allocator, config, func.name);
        defer allocator.free(target_name);

        try w.print("func {s}(\n", .{emitted_wrapper_name});
        for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
            if (isAutoCallbackParameter(auto_callback_params, function_index, parameter_index)) {
                const helper_type_name = try renderEffectiveCallbackFuncTypeName(
                    allocator,
                    decls,
                    auto_callback_params,
                    .{
                        .function_index = function_index,
                        .parameter_index = parameter_index,
                    },
                );
                defer allocator.free(helper_type_name);
                const emitted_helper_type_name = try renderTypeName(allocator, config, helper_type_name);
                defer allocator.free(emitted_helper_type_name);
                try w.print("\t{s} {s},\n", .{ param_name, emitted_helper_type_name });
                continue;
            }
            const mapped = try resolveFunctionParameterType(allocator, decls, param_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
            defer if (resolvedGoTypeNeedsFree(param_c_type, mapped)) allocator.free(mapped.go_type);
            try w.print("\t{s} {s},\n", .{ param_name, mapped.go_type });
        }
        try w.writeAll(")");

        const result_mapped = try resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
        defer if (resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
        if (result_mapped.go_type.len != 0) {
            try w.print(" {s} {{\n", .{result_mapped.go_type});
        } else {
            try w.writeAll(" {\n");
        }

        for (func.parameter_names, 0..) |param_name, parameter_index| {
            if (!isAutoCallbackParameter(auto_callback_params, function_index, parameter_index)) continue;
            try w.print("\t{s}_callback := uintptr(0)\n", .{param_name});
            try w.print("\tif {s} != nil {{\n", .{param_name});
            try w.print("\t\t{s}_callback = purego.NewCallback({s})\n", .{ param_name, param_name });
            try w.writeAll("\t}\n");
        }

        if (result_mapped.go_type.len != 0) {
            try w.print("\treturn {s}(\n", .{target_name});
        } else {
            try w.print("\t{s}(\n", .{target_name});
        }
        for (func.parameter_names, 0..) |param_name, parameter_index| {
            if (isAutoCallbackParameter(auto_callback_params, function_index, parameter_index)) {
                try w.print("\t\t{s}_callback,\n", .{param_name});
                continue;
            }
            try w.print("\t\t{s},\n", .{param_name});
        }
        try w.writeAll("\t)\n");
        try w.writeAll("}\n");
    }
}

fn writeStructAccessors(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    var wrote_any = false;
    for (decls.typedefs.items) |typedef_decl| {
        for (typedef_decl.accessor_fields) |field| {
            if (wrote_any) try w.writeByte('\n');
            wrote_any = true;
            const type_name = try renderTypeName(allocator, config, typedef_decl.name);
            defer allocator.free(type_name);
            const getter_base = try std.fmt.allocPrint(allocator, "Get_{s}", .{field.name});
            defer allocator.free(getter_base);
            const getter_name = try renderFuncName(allocator, config, getter_base);
            defer allocator.free(getter_name);
            const setter_base = try std.fmt.allocPrint(allocator, "Set_{s}", .{field.name});
            defer allocator.free(setter_base);
            const setter_name = try renderFuncName(allocator, config, setter_base);
            defer allocator.free(setter_name);
            try w.print("func (s *{s}) {s}() {s} {{\n", .{ type_name, getter_name, field.go_type });
            try w.print("\treturn s.{s}\n", .{field.name});
            try w.writeAll("}\n\n");
            try w.print("func (s *{s}) {s}(v {s}) {{\n", .{ type_name, setter_name, field.go_type });
            try w.print("\ts.{s} = v\n", .{field.name});
            try w.writeAll("}\n");
        }
    }
}

fn writeRegisterFunctions(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    const register_name = try std.fmt.allocPrint(allocator, "{s}_register_functions", .{config.lib_id});
    defer allocator.free(register_name);
    const emitted_register_name = try renderFuncName(allocator, config, register_name);
    defer allocator.free(emitted_register_name);
    try w.print("func {s}(handle uintptr) error {{\n", .{emitted_register_name});
    for (decls.functions.items) |func| {
        const emitted_func_name = try renderFuncName(allocator, config, func.name);
        defer allocator.free(emitted_func_name);
        try w.print("\t{s}_symbol, err := purego.Dlsym(handle, \"{s}\")\n", .{ emitted_func_name, func.name });
        try w.writeAll("\tif err != nil {\n");
        try w.print(
            "\t\treturn fmt.Errorf(\"purego-gen: failed to resolve function symbol {s}: %w\", err)\n",
            .{func.name},
        );
        try w.writeAll("\t}\n");
        try w.print("\tpurego.RegisterFunc(&{s}, {s}_symbol)\n", .{ emitted_func_name, emitted_func_name });
    }
    try w.writeAll("\treturn nil\n");
    try w.writeAll("}\n");
}

fn writeOwnedStringReturnHelpers(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    if (config.owned_string_return_helpers.len == 0) return;

    const gostring_name = try renderFuncName(allocator, config, "gostring");
    defer allocator.free(gostring_name);

    for (config.owned_string_return_helpers) |helper| {
        const func = findFunctionByName(decls, helper.function_name) orelse return error.OwnedStringHelperTargetFunctionNotFound;
        const free_func = findFunctionByName(decls, helper.free_func_name) orelse return error.OwnedStringHelperFreeFunctionNotFound;
        _ = free_func;

        const helper_base = try std.fmt.allocPrint(allocator, "{s}_string", .{func.name});
        defer allocator.free(helper_base);
        const helper_name = try renderFuncName(allocator, config, helper_base);
        defer allocator.free(helper_name);
        const target_name = try renderFuncName(allocator, config, func.name);
        defer allocator.free(target_name);
        const free_name = try renderFuncName(allocator, config, helper.free_func_name);
        defer allocator.free(free_name);

        try w.print("func {s}(\n", .{helper_name});
        for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
            const mapped = try resolveFunctionParameterType(
                allocator,
                decls,
                param_c_type,
                false,
                containsEmitKind(config.emit, .type),
                config.strict_enum_typedefs,
            );
            _ = parameter_index;
            defer if (resolvedGoTypeNeedsFree(param_c_type, mapped)) allocator.free(mapped.go_type);
            if (mapped.comment) |comment| {
                try w.print("\t// C: {s}\n", .{comment});
            }
            try w.print("\t{s} {s},\n", .{ param_name, mapped.go_type });
        }
        try w.writeAll(") string {\n");
        try w.print("\trawPtr := {s}(\n", .{target_name});
        for (func.parameter_names) |param_name| {
            try w.print("\t\t{s},\n", .{param_name});
        }
        try w.writeAll("\t)\n");
        try w.print("\tresult := {s}(rawPtr)\n", .{gostring_name});
        try w.writeAll("\tif rawPtr != 0 {\n");
        try w.print("\t\t{s}(rawPtr)\n", .{free_name});
        try w.writeAll("\t}\n");
        try w.writeAll("\treturn result\n");
        try w.writeAll("}\n\n");
    }

    try w.writeByte('\n');
    try w.print("func {s}(ptr uintptr) string {{\n", .{gostring_name});
    try w.writeAll("\tif ptr == 0 {\n");
    try w.writeAll("\t\treturn \"\"\n");
    try w.writeAll("\t}\n");
    try w.writeAll("\tp := *(*unsafe.Pointer)(unsafe.Pointer(&ptr))\n");
    try w.writeAll("\tvar n int\n");
    try w.writeAll("\tfor *(*byte)(unsafe.Add(p, n)) != 0 {\n");
    try w.writeAll("\t\tn++\n");
    try w.writeAll("\t}\n");
    try w.writeAll("\treturn strings.Clone(unsafe.String((*byte)(p), n))\n");
    try w.writeAll("}\n");
}

fn writePublicApiWrappers(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    var emitted_any = false;
    for (decls.functions.items) |func| {
        if (!matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_include)) continue;
        if (matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_exclude)) continue;

        emitted_any = true;
        const public_name = try renderPublicApiName(
            allocator,
            config.public_api.strip_prefix,
            config.public_api.wrappers_overrides,
            func.name,
        );
        defer allocator.free(public_name);
        const target_name = try renderFuncName(allocator, config, func.name);
        defer allocator.free(target_name);

        try w.print("func {s}(\n", .{public_name});
        for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
            const public_go_type = try resolvePublicApiGoType(allocator, config, decls, param_c_type, containsEmitKind(config.emit, .type));
            defer allocator.free(public_go_type);
            try w.print("\t{s} {s},\n", .{ param_name, public_go_type });
        }
        try w.writeAll(")");

        const result_go_type = try resolvePublicApiGoType(allocator, config, decls, func.result_c_type, containsEmitKind(config.emit, .type));
        defer allocator.free(result_go_type);
        if (result_go_type.len != 0) {
            try w.print(" {s} {{\n", .{result_go_type});
            try w.print("\treturn {s}(\n", .{target_name});
        } else {
            try w.writeAll(" {\n");
            try w.print("\t{s}(\n", .{target_name});
        }
        for (func.parameter_names) |param_name| {
            try w.print("\t\t{s},\n", .{param_name});
        }
        try w.writeAll("\t)\n");
        try w.writeAll("}\n");
    }

    if (emitted_any) try w.writeByte('\n');
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

fn writeConstants(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    if (decls.constants.items.len == 0) return;
    try w.writeAll("const (\n");
    for (decls.constants.items, 0..) |constant_decl, index| {
        try writeComment(w, "\t", constant_decl.comment);
        const emitted_name = try renderConstName(allocator, config, constant_decl.name);
        defer allocator.free(emitted_name);
        const typed_prefix = if (config.typed_sentinel_constants and constant_decl.typed_go_type != null)
            try std.fmt.allocPrint(allocator, " {s}", .{constant_decl.typed_go_type.?})
        else
            try allocator.dupe(u8, "");
        defer allocator.free(typed_prefix);
        if (index == 0) {
            try w.print("\t{s}{s} = {s}\n", .{ emitted_name, typed_prefix, constant_decl.value_expr });
            continue;
        }
        try w.print("\t{s}{s} = {s}\n", .{ emitted_name, typed_prefix, constant_decl.value_expr });
    }
    try w.writeAll(")\n");
}

fn writeRuntimeVars(
    allocator: std.mem.Allocator,
    w: anytype,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) !void {
    if (decls.runtime_vars.items.len == 0) return;
    try w.writeAll("var (\n");
    for (decls.runtime_vars.items) |runtime_var_decl| {
        _ = runtime_var_decl.c_type;
        try writeComment(w, "\t", runtime_var_decl.comment);
        const emitted_var_name = try renderRuntimeVarName(allocator, config, runtime_var_decl.name);
        defer allocator.free(emitted_var_name);
        try w.print("\t{s} uintptr\n", .{emitted_var_name});
    }
    try w.writeAll(")\n\n");

    const load_name = try std.fmt.allocPrint(allocator, "{s}_load_runtime_vars", .{config.lib_id});
    defer allocator.free(load_name);
    const emitted_load_name = try renderFuncName(allocator, config, load_name);
    defer allocator.free(emitted_load_name);
    try w.print("func {s}(handle uintptr) error {{\n", .{emitted_load_name});
    for (decls.runtime_vars.items) |runtime_var_decl| {
        const emitted_var_name = try renderRuntimeVarName(allocator, config, runtime_var_decl.name);
        defer allocator.free(emitted_var_name);
        try w.print(
            "\t{s}_symbol, err := purego.Dlsym(handle, \"{s}\")\n",
            .{ emitted_var_name, runtime_var_decl.name },
        );
        try w.writeAll("\tif err != nil {\n");
        try w.print(
            "\t\treturn fmt.Errorf(\n\t\t\t\"purego-gen: failed to resolve runtime var symbol {s}: %w\",\n\t\t\terr,\n\t\t)\n",
            .{runtime_var_decl.name},
        );
        try w.writeAll("\t}\n");
        try w.print("\t{s} = {s}_symbol\n", .{ emitted_var_name, emitted_var_name });
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

fn renderTypeAliasItem(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    typedef_decl: declarations.TypedefDecl,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeComment(w, "\t", typedef_decl.comment);
    if (config.strict_enum_typedefs and typedef_decl.is_enum_typedef and typedef_decl.underlying_go_type != null) {
        const emitted_name = try renderTypeName(allocator, config, typedef_decl.name);
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
    return try buffer.toOwnedSlice(allocator);
}

fn renderFunctionVarItem(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    func: declarations.FunctionDecl,
    function_index: usize,
    callback_params: []const AutoCallbackParam,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeComment(w, "\t", func.comment);
    const func_name = try renderFuncName(allocator, config, func.name);
    defer allocator.free(func_name);
    try w.print("\t{s} func", .{func_name});
    if (func.parameter_names.len == 0) {
        try w.writeAll("()");
    } else {
        try w.writeAll("(\n");
        for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
            const mapped = try resolveFunctionParameterType(
                allocator,
                decls,
                param_c_type,
                isAutoCallbackParameter(callback_params, function_index, parameter_index),
                containsEmitKind(config.emit, .type),
                config.strict_enum_typedefs,
            );
            defer if (resolvedGoTypeNeedsFree(param_c_type, mapped) and !isAutoCallbackParameter(callback_params, function_index, parameter_index)) allocator.free(mapped.go_type);
            if (mapped.comment) |comment| {
                try w.print("\t\t// C: {s}\n", .{comment});
            }
            try w.print("\t\t{s} {s},\n", .{ param_name, mapped.go_type });
        }
        const result_mapped = if (isOwnedStringReturnTarget(config, func.name))
            CTypeMapping{ .go_type = "uintptr", .comment = func.result_c_type }
        else
            try resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
        defer if (resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
        if (result_mapped.comment) |comment| {
            try w.print("\t\t// C: {s}\n", .{comment});
        }
        try w.writeAll("\t)");
    }

    const result_mapped = if (isOwnedStringReturnTarget(config, func.name))
        CTypeMapping{ .go_type = "uintptr", .comment = func.result_c_type }
    else
        try resolveFunctionParameterType(allocator, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
    defer if (resolvedGoTypeNeedsFree(func.result_c_type, result_mapped)) allocator.free(result_mapped.go_type);
    if (result_mapped.go_type.len != 0) {
        try w.print(" {s}\n", .{result_mapped.go_type});
    } else {
        try w.writeByte('\n');
    }
    return try buffer.toOwnedSlice(allocator);
}

fn renderAutoCallbackTypeItem(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    auto_callback_params: []const AutoCallbackParam,
    auto_callback: AutoCallbackParam,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    const func = decls.functions.items[auto_callback.function_index];
    const helper_type_name = try renderEffectiveCallbackFuncTypeName(
        allocator,
        decls,
        auto_callback_params,
        auto_callback,
    );
    defer allocator.free(helper_type_name);
    const emitted_helper_type_name = try renderTypeName(allocator, config, helper_type_name);
    defer allocator.free(emitted_helper_type_name);
    const go_signature = try renderCallbackGoSignature(
        allocator,
        decls,
        func.parameter_c_types[auto_callback.parameter_index],
    );
    defer allocator.free(go_signature);

    try w.print("\t// C: {s}\n", .{func.parameter_c_types[auto_callback.parameter_index]});
    try w.print("\t{s} = {s}\n", .{ emitted_helper_type_name, go_signature });
    return try buffer.toOwnedSlice(allocator);
}

fn renderBufferHelperItem(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    func: declarations.FunctionDecl,
    pairs: []const BufferPairIndices,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    try writeBufferHelper(allocator, buffer.writer(allocator), config, func, pairs);
    return try buffer.toOwnedSlice(allocator);
}

fn appendBlockSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    kind: []const u8,
    block_items: []const []const u8,
    force_block: bool,
    add_leading_gap: bool,
) !void {
    if (!force_block and block_items.len == 0) return;
    try sections.append(allocator, .{
        .kind = kind,
        .leading_gap = has_emitted_section.* and add_leading_gap,
        .block_items = block_items,
        .text_items = &.{},
    });
    has_emitted_section.* = true;
}

fn appendTextSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    text_items: []const []const u8,
    add_leading_gap: bool,
) !void {
    if (text_items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "text",
        .leading_gap = has_emitted_section.* and add_leading_gap,
        .block_items = &.{},
        .text_items = text_items,
    });
    has_emitted_section.* = true;
}

fn appendRegisterFunctionsSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    add_leading_gap: bool,
    register_functions_name: []const u8,
    items: []const TemplateRegisterFunctionView,
) !void {
    if (items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "register_functions",
        .leading_gap = has_emitted_section.* and add_leading_gap,
        .block_items = &.{},
        .text_items = &.{},
        .register_functions_name = register_functions_name,
        .register_function_items = items,
    });
    has_emitted_section.* = true;
}

fn appendRuntimeVarLoaderSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    add_leading_gap: bool,
    load_runtime_vars_name: []const u8,
    items: []const TemplateRegisterFunctionView,
) !void {
    if (load_runtime_vars_name.len == 0) return;
    try sections.append(allocator, .{
        .kind = "runtime_var_loader",
        .leading_gap = has_emitted_section.* and add_leading_gap,
        .block_items = &.{},
        .text_items = &.{},
        .load_runtime_vars_name = load_runtime_vars_name,
        .runtime_var_symbol_items = items,
    });
    has_emitted_section.* = true;
}

fn appendAutoCallbackConstructorsSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    items: []const AutoCallbackConstructorView,
) !void {
    if (items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "auto_callback_constructors",
        .leading_gap = false,
        .block_items = &.{},
        .text_items = &.{},
        .auto_callback_constructor_items = items,
    });
    has_emitted_section.* = true;
}

fn appendStructAccessorsSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    items: []const StructAccessorView,
) !void {
    if (items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "struct_accessors",
        .leading_gap = false,
        .block_items = &.{},
        .text_items = &.{},
        .struct_accessor_items = items,
    });
    has_emitted_section.* = true;
}

fn appendUnionHelpersSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
) !void {
    try sections.append(allocator, .{
        .kind = "union_helpers",
        .leading_gap = false,
        .block_items = &.{},
        .text_items = &.{},
    });
    has_emitted_section.* = true;
}

fn appendPublicWrappersSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    items: []const PublicWrapperView,
) !void {
    if (items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "public_wrappers",
        .leading_gap = has_emitted_section.*,
        .block_items = &.{},
        .text_items = &.{},
        .public_wrapper_items = items,
    });
    has_emitted_section.* = true;
}

fn appendAutoCallbackWrappersSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    items: []const AutoCallbackWrapperView,
) !void {
    if (items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "auto_callback_wrappers",
        .leading_gap = false,
        .block_items = &.{},
        .text_items = &.{},
        .auto_callback_wrapper_items = items,
    });
    has_emitted_section.* = true;
}

fn appendOwnedStringHelpersSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    items: []const OwnedStringHelperView,
    gostring_name: []const u8,
) !void {
    if (items.len == 0 and gostring_name.len == 0) return;
    try sections.append(allocator, .{
        .kind = "owned_string_helpers",
        .leading_gap = false,
        .block_items = &.{},
        .text_items = &.{},
        .owned_string_helper_items = items,
        .gostring_name = gostring_name,
    });
    has_emitted_section.* = true;
}

fn appendConstBlockSection(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(TemplateSectionView),
    has_emitted_section: *bool,
    const_items: []const ConstantItemView,
    add_leading_gap: bool,
) !void {
    if (const_items.len == 0) return;
    try sections.append(allocator, .{
        .kind = "const_block",
        .leading_gap = has_emitted_section.* and add_leading_gap,
        .block_items = &.{},
        .text_items = &.{},
        .const_items = const_items,
    });
    has_emitted_section.* = true;
}

fn buildImportBlock(
    allocator: std.mem.Allocator,
    need_fmt: bool,
    need_unsafe: bool,
    need_purego: bool,
    need_strings: bool,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try w.writeAll("import (\n");
    if (need_fmt) {
        try w.writeAll("\t\"fmt\"\n");
    }
    if (need_strings) {
        try w.writeAll("\t\"strings\"\n");
    }
    if (need_unsafe) {
        try w.writeAll("\t\"unsafe\"\n");
    }
    if ((need_fmt and (need_unsafe or need_purego)) or (need_strings and (need_unsafe or need_purego)) or (need_unsafe and need_purego)) {
        try w.writeByte('\n');
    }
    if (need_purego) {
        try w.writeAll("\t\"github.com/ebitengine/purego\"\n");
    }
    try w.writeAll(")\n\n");
    return try buffer.toOwnedSlice(allocator);
}

fn buildBlankIdentifierBlock(
    allocator: std.mem.Allocator,
    need_fmt: bool,
    need_unsafe: bool,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try w.writeAll("var (\n");
    if (need_fmt) {
        try w.writeAll("\t_ = fmt.Errorf\n");
    }
    if (need_unsafe) {
        try w.writeAll("\t_ = unsafe.Pointer(nil)\n");
    }
    try w.writeAll(")\n\n");
    return try buffer.toOwnedSlice(allocator);
}

fn buildTypesSection(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeTypedefs(allocator, w, config, decls);
    if (hasPublicTypeAliases(config, decls)) {
        try writePublicTypeAliases(allocator, w, config, decls);
        try w.writeByte('\n');
    } else {
        try w.writeByte('\n');
    }
    return try buffer.toOwnedSlice(allocator);
}

fn buildCallbacksSection(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    callback_params: []const AutoCallbackParam,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeAutoCallbackTypes(allocator, w, config, decls, callback_params);
    try w.writeByte('\n');
    try writeAutoCallbackConstructors(allocator, w, config, decls, callback_params);
    return try buffer.toOwnedSlice(allocator);
}

fn buildConstantsSection(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeConstants(allocator, w, config, decls);
    try w.writeByte('\n');
    return try buffer.toOwnedSlice(allocator);
}

fn buildStructAccessorsSection(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeStructAccessors(allocator, w, config, decls);
    try w.writeByte('\n');
    return try buffer.toOwnedSlice(allocator);
}

fn buildHelpersSection(
    allocator: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writeHelperFunctions(w, decls);
    return try buffer.toOwnedSlice(allocator);
}

fn buildFunctionsSection(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    callback_params: []const AutoCallbackParam,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    try writePublicApiWrappers(allocator, w, config, decls);
    try writeFunctions(allocator, w, config, decls, callback_params);
    try w.writeByte('\n');
    try writeBufferHelpers(allocator, w, config, decls);
    if (config.buffer_param_helpers.len > 0) {
        try w.writeByte('\n');
    }
    try writeAutoCallbackWrappers(allocator, w, config, decls, callback_params);
    if (callback_params.len > 0) {
        try w.writeByte('\n');
    }
    try writeOwnedStringReturnHelpers(allocator, w, config, decls);
    if (config.owned_string_return_helpers.len > 0) {
        try w.writeByte('\n');
    }
    try writeRegisterFunctions(allocator, w, config, decls);
    return try buffer.toOwnedSlice(allocator);
}

fn buildRuntimeVarsSection(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    needs_leading_separator: bool,
) ![]u8 {
    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    const w = buffer.writer(allocator);

    if (needs_leading_separator) {
        try w.writeByte('\n');
    }
    try writeRuntimeVars(allocator, w, config, decls);
    return try buffer.toOwnedSlice(allocator);
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
    const need_unsafe = emits_functions or declarationsNeedUnsafe(decls) or declarationsNeedPurego(decls);
    const need_fmt = declarationsNeedFmt(emits_functions, has_emitted_runtime_vars, decls);
    const need_strings = config.owned_string_return_helpers.len > 0;
    const has_helper_functions = declarationsHaveHelperFunctions(decls);
    const callback_params = if (emits_functions and config.callback_param_helpers.len > 0)
        try collectExplicitCallbackParams(allocator, decls, config.callback_param_helpers)
    else if (config.auto_callbacks and emits_functions)
        try collectAutoCallbackParams(allocator, decls)
    else
        try allocator.alloc(AutoCallbackParam, 0);
    defer allocator.free(callback_params);

    var arena_state = std.heap.ArenaAllocator.init(allocator);
    defer arena_state.deinit();
    const arena = arena_state.allocator();

    var std_imports: std.ArrayList([]const u8) = .empty;
    if (need_fmt) try std_imports.append(arena, "fmt");
    if (need_strings) try std_imports.append(arena, "strings");
    if (need_unsafe) try std_imports.append(arena, "unsafe");
    const std_import_items = try std_imports.toOwnedSlice(arena);

    var blank_identifiers: std.ArrayList([]const u8) = .empty;
    if (need_fmt) try blank_identifiers.append(arena, "fmt.Errorf");
    if (need_unsafe) try blank_identifiers.append(arena, "unsafe.Pointer(nil)");
    const blank_identifier_items = try blank_identifiers.toOwnedSlice(arena);

    var type_alias_items: std.ArrayList([]const u8) = .empty;
    var helper_type_alias_items: std.ArrayList([]const u8) = .empty;
    if (emits_types) {
        for (decls.typedefs.items) |typedef_decl| {
            try type_alias_items.append(arena, try renderTypeAliasItem(arena, config, typedef_decl));
            if (typedef_decl.helper_type_definition) |helper_type_definition| {
                try helper_type_alias_items.append(arena, helper_type_definition);
            }
        }
    }
    const type_alias_texts = try type_alias_items.toOwnedSlice(arena);
    const helper_type_alias_texts = try helper_type_alias_items.toOwnedSlice(arena);
    const type_block_items = blk: {
        var items: std.ArrayList([]const u8) = .empty;
        for (type_alias_texts) |item| try items.append(arena, item);
        for (helper_type_alias_texts) |item| try items.append(arena, item);
        break :blk try items.toOwnedSlice(arena);
    };

    var public_type_alias_items: std.ArrayList([]const u8) = .empty;
    if (emits_types) {
        for (decls.typedefs.items) |typedef_decl| {
            if (!matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) continue;
            const public_name = try renderPublicApiName(
                arena,
                config.public_api.strip_prefix,
                config.public_api.type_aliases_overrides,
                typedef_decl.name,
            );
            const emitted_internal_name = try renderTypeName(arena, config, typedef_decl.name);
            try public_type_alias_items.append(arena, try std.fmt.allocPrint(arena, "\t{s} = {s}\n", .{ public_name, emitted_internal_name }));
        }
    }
    const public_type_alias_texts = try public_type_alias_items.toOwnedSlice(arena);

    var auto_callback_type_items: std.ArrayList([]const u8) = .empty;
    var emitted_callback_type_names: std.ArrayList([]const u8) = .empty;
    if (callback_params.len > 0) {
        for (callback_params) |auto_callback| {
            const helper_type_name = try renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, auto_callback);
            const emitted_helper_type_name = try renderTypeName(arena, config, helper_type_name);
            if (containsString(emitted_callback_type_names.items, emitted_helper_type_name)) continue;
            try auto_callback_type_items.append(arena, try renderAutoCallbackTypeItem(arena, config, decls, callback_params, auto_callback));
            try emitted_callback_type_names.append(arena, emitted_helper_type_name);
        }
    }
    const auto_callback_type_texts = try auto_callback_type_items.toOwnedSlice(arena);

    var auto_callback_constructor_views: std.ArrayList(AutoCallbackConstructorView) = .empty;
    var emitted_callback_constructor_names: std.ArrayList([]const u8) = .empty;
    if (callback_params.len > 0) {
        for (callback_params) |auto_callback| {
            const helper_type_name = try renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, auto_callback);
            const emitted_helper_type_name = try renderTypeName(arena, config, helper_type_name);
            const constructor_name = try renderEffectiveCallbackConstructorName(arena, decls, callback_params, auto_callback);
            const emitted_constructor_name = try renderFuncName(arena, config, constructor_name);
            if (containsString(emitted_callback_constructor_names.items, emitted_constructor_name)) continue;
            try auto_callback_constructor_views.append(arena, .{
                .constructor_name = emitted_constructor_name,
                .type_name = emitted_helper_type_name,
            });
            try emitted_callback_constructor_names.append(arena, emitted_constructor_name);
        }
    }
    const auto_callback_constructor_view_items = try auto_callback_constructor_views.toOwnedSlice(arena);

    var constant_views: std.ArrayList(ConstantItemView) = .empty;
    if (emits_constants) {
        for (decls.constants.items) |constant_decl| {
            var comment_buf: std.ArrayList(u8) = .empty;
            const cw = comment_buf.writer(arena);
            try writeComment(cw, "\t", constant_decl.comment);
            const comment_str = try comment_buf.toOwnedSlice(arena);
            const emitted_name = try renderConstName(arena, config, constant_decl.name);
            const typed_prefix = if (config.typed_sentinel_constants and constant_decl.typed_go_type != null)
                try std.fmt.allocPrint(arena, " {s}", .{constant_decl.typed_go_type.?})
            else
                try arena.dupe(u8, "");
            try constant_views.append(arena, .{
                .comment = comment_str,
                .name = emitted_name,
                .typed_prefix = typed_prefix,
                .value_expr = constant_decl.value_expr,
            });
        }
    }
    const constant_view_items = try constant_views.toOwnedSlice(arena);

    var struct_accessor_views: std.ArrayList(StructAccessorView) = .empty;
    if (emits_struct_accessors) {
        for (decls.typedefs.items) |typedef_decl| {
            const type_name = try renderTypeName(arena, config, typedef_decl.name);
            for (typedef_decl.accessor_fields) |field| {
                const getter_base = try std.fmt.allocPrint(arena, "Get_{s}", .{field.name});
                const getter_name = try renderFuncName(arena, config, getter_base);
                const setter_base = try std.fmt.allocPrint(arena, "Set_{s}", .{field.name});
                const setter_name = try renderFuncName(arena, config, setter_base);
                try struct_accessor_views.append(arena, .{
                    .type_name = type_name,
                    .getter_name = getter_name,
                    .setter_name = setter_name,
                    .field_name = field.name,
                    .go_type = field.go_type,
                });
            }
        }
    }
    const struct_accessor_view_items = try struct_accessor_views.toOwnedSlice(arena);

    var helper_items: std.ArrayList([]const u8) = .empty;
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.helper_function_definition) |text| {
            try helper_items.append(arena, try std.fmt.allocPrint(arena, "{s}\n", .{text}));
        }
    }
    const helper_texts = try helper_items.toOwnedSlice(arena);
    const need_union_helpers = declarationsNeedUnionHelpers(decls);

    var public_wrapper_views: std.ArrayList(PublicWrapperView) = .empty;
    var function_var_items: std.ArrayList([]const u8) = .empty;
    var buffer_helper_items: std.ArrayList([]const u8) = .empty;
    var auto_callback_wrapper_views: std.ArrayList(AutoCallbackWrapperView) = .empty;
    var owned_string_helper_views: std.ArrayList(OwnedStringHelperView) = .empty;
    var gostring_name_str: []const u8 = "";
    var register_functions: std.ArrayList(TemplateRegisterFunctionView) = .empty;

    if (emits_functions) {
        for (decls.functions.items) |func| {
            if (matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_include) and
                !matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_exclude))
            {
                const public_name = try renderPublicApiName(arena, config.public_api.strip_prefix, config.public_api.wrappers_overrides, func.name);
                const target_name = try renderFuncName(arena, config, func.name);
                const result_type = try resolvePublicApiGoType(arena, config, decls, func.result_c_type, containsEmitKind(config.emit, .type));
                var params: std.ArrayList(PublicWrapperParamView) = .empty;
                for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
                    const go_type = try resolvePublicApiGoType(arena, config, decls, param_c_type, containsEmitKind(config.emit, .type));
                    try params.append(arena, .{ .name = param_name, .go_type = go_type });
                }
                try public_wrapper_views.append(arena, .{
                    .public_name = public_name,
                    .target_name = target_name,
                    .params = try params.toOwnedSlice(arena),
                    .result_type = result_type,
                });
            }
        }

        for (decls.functions.items, 0..) |func, function_index| {
            try function_var_items.append(arena, try renderFunctionVarItem(arena, config, decls, func, function_index, callback_params));
            const emitted_func_name = try renderFuncName(arena, config, func.name);
            try register_functions.append(arena, .{ .name = emitted_func_name, .symbol = func.name });
        }

        var explicit_names: std.ArrayList([]const u8) = .empty;
        for (config.buffer_param_helpers) |helper| {
            switch (helper) {
                .explicit => |explicit| try explicit_names.append(arena, explicit.function_name),
                .pattern => {},
            }
        }
        var emitted_buffer_names: std.ArrayList([]const u8) = .empty;
        for (config.buffer_param_helpers) |helper| {
            switch (helper) {
                .explicit => |explicit| {
                    const func = findFunctionByName(decls, explicit.function_name) orelse return error.BufferHelperTargetFunctionNotFound;
                    const pairs = try resolveExplicitBufferPairs(arena, func, explicit.pairs);
                    try buffer_helper_items.append(arena, try renderBufferHelperItem(arena, config, func, pairs));
                    try emitted_buffer_names.append(arena, func.name);
                },
                .pattern => |pattern| {
                    const function_count = decls.functions.items.len;
                    const indices = try arena.alloc(usize, function_count);
                    for (indices, 0..) |*slot, index| slot.* = index;
                    sortFunctionIndicesByName(indices, decls.functions.items);

                    var match_count: usize = 0;
                    for (indices) |index| {
                        const func = decls.functions.items[index];
                        if (containsString(explicit_names.items, func.name)) continue;
                        if (containsString(emitted_buffer_names.items, func.name)) continue;
                        if (!functionNameMatchesPattern(func.name, pattern.function_pattern)) continue;
                        const pairs = try detectBufferPairs(arena, func);
                        if (pairs.len == 0) continue;
                        try buffer_helper_items.append(arena, try renderBufferHelperItem(arena, config, func, pairs));
                        try emitted_buffer_names.append(arena, func.name);
                        match_count += 1;
                    }
                    if (match_count == 0) return error.BufferPatternMatchedNoFunctions;
                },
            }
        }

        for (decls.functions.items, 0..) |func, function_index| {
            if (!hasAutoCallbackParamForFunction(callback_params, function_index)) continue;
            const wrapper_name_base = try std.fmt.allocPrint(arena, "{s}_callbacks", .{func.name});
            const wrapper_name = try renderFuncName(arena, config, wrapper_name_base);
            const target_name = try renderFuncName(arena, config, func.name);
            const result_mapped = try resolveFunctionParameterType(arena, decls, func.result_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
            var params: std.ArrayList(AutoCallbackWrapperParamView) = .empty;
            for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
                if (isAutoCallbackParameter(callback_params, function_index, parameter_index)) {
                    const helper_type_name = try renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, .{
                        .function_index = function_index,
                        .parameter_index = parameter_index,
                    });
                    const emitted_type = try renderTypeName(arena, config, helper_type_name);
                    try params.append(arena, .{ .name = param_name, .go_type = emitted_type, .is_callback = true });
                } else {
                    const mapped = try resolveFunctionParameterType(arena, decls, param_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
                    try params.append(arena, .{ .name = param_name, .go_type = mapped.go_type, .is_callback = false });
                }
            }
            try auto_callback_wrapper_views.append(arena, .{
                .wrapper_name = wrapper_name,
                .target_name = target_name,
                .params = try params.toOwnedSlice(arena),
                .result_type = result_mapped.go_type,
            });
        }

        for (config.owned_string_return_helpers) |helper| {
            const func = findFunctionByName(decls, helper.function_name) orelse return error.OwnedStringHelperTargetFunctionNotFound;
            _ = findFunctionByName(decls, helper.free_func_name) orelse return error.OwnedStringHelperFreeFunctionNotFound;
            const helper_base = try std.fmt.allocPrint(arena, "{s}_string", .{func.name});
            const helper_name = try renderFuncName(arena, config, helper_base);
            const target_name = try renderFuncName(arena, config, func.name);
            const free_name = try renderFuncName(arena, config, helper.free_func_name);
            const gostring_n = try renderFuncName(arena, config, "gostring");
            var params: std.ArrayList(OwnedStringHelperParamView) = .empty;
            for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
                const mapped = try resolveFunctionParameterType(arena, decls, param_c_type, false, containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
                try params.append(arena, .{
                    .name = param_name,
                    .go_type = mapped.go_type,
                    .c_comment = mapped.comment orelse "",
                });
            }
            try owned_string_helper_views.append(arena, .{
                .helper_name = helper_name,
                .target_name = target_name,
                .free_name = free_name,
                .gostring_name = gostring_n,
                .params = try params.toOwnedSlice(arena),
            });
        }
        if (config.owned_string_return_helpers.len > 0) {
            gostring_name_str = try renderFuncName(arena, config, "gostring");
        }
    }
    const public_wrapper_view_items = try public_wrapper_views.toOwnedSlice(arena);
    const function_var_texts = try function_var_items.toOwnedSlice(arena);
    const buffer_helper_texts = try buffer_helper_items.toOwnedSlice(arena);
    const auto_callback_wrapper_view_items = try auto_callback_wrapper_views.toOwnedSlice(arena);
    const owned_string_helper_view_items = try owned_string_helper_views.toOwnedSlice(arena);
    const register_function_items = try register_functions.toOwnedSlice(arena);

    var runtime_var_items: std.ArrayList([]const u8) = .empty;
    var runtime_var_symbols: std.ArrayList(TemplateRegisterFunctionView) = .empty;
    if (emits_runtime_vars) {
        for (decls.runtime_vars.items) |runtime_var_decl| {
            var buffer: std.ArrayList(u8) = .empty;
            const w = buffer.writer(arena);
            try writeComment(w, "\t", runtime_var_decl.comment);
            const emitted_var_name = try renderRuntimeVarName(arena, config, runtime_var_decl.name);
            try w.print("\t{s} uintptr\n", .{emitted_var_name});
            try runtime_var_items.append(arena, try buffer.toOwnedSlice(arena));
            try runtime_var_symbols.append(arena, .{ .name = emitted_var_name, .symbol = runtime_var_decl.name });
        }
    }
    const runtime_var_texts = try runtime_var_items.toOwnedSlice(arena);
    const runtime_var_symbol_items = try runtime_var_symbols.toOwnedSlice(arena);

    const register_functions_name = if (emits_functions)
        try renderFuncName(arena, config, try std.fmt.allocPrint(arena, "{s}_register_functions", .{config.lib_id}))
    else
        "";
    const load_runtime_vars_name = if (emits_runtime_vars)
        try renderFuncName(arena, config, try std.fmt.allocPrint(arena, "{s}_load_runtime_vars", .{config.lib_id}))
    else
        "";

    var sections: std.ArrayList(TemplateSectionView) = .empty;
    var has_emitted_section = false;
    try appendBlockSection(arena, &sections, &has_emitted_section, "type_block", type_block_items, false, true);
    try appendBlockSection(arena, &sections, &has_emitted_section, "type_block", public_type_alias_texts, false, false);
    try appendBlockSection(arena, &sections, &has_emitted_section, "type_block", auto_callback_type_texts, false, false);
    try appendAutoCallbackConstructorsSection(arena, &sections, &has_emitted_section, auto_callback_constructor_view_items);
    if (emits_constants and !has_helper_functions) {
        try appendConstBlockSection(arena, &sections, &has_emitted_section, constant_view_items, true);
    }
    try appendStructAccessorsSection(arena, &sections, &has_emitted_section, struct_accessor_view_items);
    try appendTextSection(arena, &sections, &has_emitted_section, helper_texts, false);
    if (need_union_helpers) {
        try appendUnionHelpersSection(arena, &sections, &has_emitted_section);
    }
    if (emits_constants and has_helper_functions) {
        try appendConstBlockSection(arena, &sections, &has_emitted_section, constant_view_items, true);
    }
    try appendPublicWrappersSection(arena, &sections, &has_emitted_section, public_wrapper_view_items);
    try appendBlockSection(arena, &sections, &has_emitted_section, "var_block", function_var_texts, emits_functions, true);
    try appendTextSection(arena, &sections, &has_emitted_section, buffer_helper_texts, false);
    try appendAutoCallbackWrappersSection(arena, &sections, &has_emitted_section, auto_callback_wrapper_view_items);
    try appendOwnedStringHelpersSection(arena, &sections, &has_emitted_section, owned_string_helper_view_items, gostring_name_str);
    try appendRegisterFunctionsSection(arena, &sections, &has_emitted_section, true, register_functions_name, register_function_items);
    try appendBlockSection(arena, &sections, &has_emitted_section, "var_block", runtime_var_texts, emits_runtime_vars, true);
    try appendRuntimeVarLoaderSection(arena, &sections, &has_emitted_section, true, load_runtime_vars_name, runtime_var_symbol_items);
    const section_items = try sections.toOwnedSlice(arena);

    const template_data = .{
        .package_name = config.package_name,
        .has_import_block = std_import_items.len > 0 or need_purego,
        .std_imports = std_import_items,
        .has_purego_import = need_purego,
        .has_blank_identifier_block = blank_identifier_items.len > 0,
        .blank_identifiers = blank_identifier_items,
        .sections = section_items,
    };

    var buffer: std.ArrayList(u8) = .empty;
    errdefer buffer.deinit(allocator);
    try gotmpl.render(buffer.writer(allocator), go_file_template, template_data);

    const rendered = try buffer.toOwnedSlice(allocator);
    defer allocator.free(rendered);
    return formatGoSource(allocator, rendered);
}

pub fn applyExcludeFilters(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *declarations.CollectedDeclarations,
) void {
    var next_function_index: usize = 0;
    for (decls.functions.items) |func| {
        if (isExactExcluded(config.exclude.func_name, func.name)) {
            freeFunctionDecl(allocator, func);
            continue;
        }
        decls.functions.items[next_function_index] = func;
        next_function_index += 1;
    }
    decls.functions.items.len = next_function_index;

    var next_typedef_index: usize = 0;
    for (decls.typedefs.items) |typedef_decl| {
        if (isExactExcluded(config.exclude.type_name, typedef_decl.name)) {
            freeTypedefDecl(allocator, typedef_decl);
            continue;
        }
        decls.typedefs.items[next_typedef_index] = typedef_decl;
        next_typedef_index += 1;
    }
    decls.typedefs.items.len = next_typedef_index;

    var next_constant_index: usize = 0;
    for (decls.constants.items) |constant_decl| {
        if (isExactExcluded(config.exclude.const_name, constant_decl.name)) {
            allocator.free(constant_decl.name);
            allocator.free(constant_decl.value_expr);
            if (constant_decl.comment) |comment| allocator.free(comment);
            continue;
        }
        decls.constants.items[next_constant_index] = constant_decl;
        next_constant_index += 1;
    }
    decls.constants.items.len = next_constant_index;

    var next_runtime_var_index: usize = 0;
    for (decls.runtime_vars.items) |runtime_var_decl| {
        if (isExactExcluded(config.exclude.var_name, runtime_var_decl.name)) {
            allocator.free(runtime_var_decl.name);
            allocator.free(runtime_var_decl.c_type);
            if (runtime_var_decl.comment) |comment| allocator.free(comment);
            continue;
        }
        decls.runtime_vars.items[next_runtime_var_index] = runtime_var_decl;
        next_runtime_var_index += 1;
    }
    decls.runtime_vars.items.len = next_runtime_var_index;
}

pub fn applyIncludeFilters(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *declarations.CollectedDeclarations,
) void {
    var next_function_index: usize = 0;
    for (decls.functions.items) |func| {
        if (!isIncludedOnly(config.include.func_name, func.name)) {
            freeFunctionDecl(allocator, func);
            continue;
        }
        decls.functions.items[next_function_index] = func;
        next_function_index += 1;
    }
    decls.functions.items.len = next_function_index;

    var next_typedef_index: usize = 0;
    for (decls.typedefs.items) |typedef_decl| {
        if (!isIncludedOnly(config.include.type_name, typedef_decl.name)) {
            freeTypedefDecl(allocator, typedef_decl);
            continue;
        }
        decls.typedefs.items[next_typedef_index] = typedef_decl;
        next_typedef_index += 1;
    }
    decls.typedefs.items.len = next_typedef_index;

    var next_constant_index: usize = 0;
    for (decls.constants.items) |constant_decl| {
        if (!isIncludedOnly(config.include.const_name, constant_decl.name)) {
            allocator.free(constant_decl.name);
            allocator.free(constant_decl.value_expr);
            if (constant_decl.comment) |comment| allocator.free(comment);
            continue;
        }
        decls.constants.items[next_constant_index] = constant_decl;
        next_constant_index += 1;
    }
    decls.constants.items.len = next_constant_index;

    var next_runtime_var_index: usize = 0;
    for (decls.runtime_vars.items) |runtime_var_decl| {
        if (!isIncludedOnly(config.include.var_name, runtime_var_decl.name)) {
            allocator.free(runtime_var_decl.name);
            allocator.free(runtime_var_decl.c_type);
            if (runtime_var_decl.comment) |comment| allocator.free(comment);
            continue;
        }
        decls.runtime_vars.items[next_runtime_var_index] = runtime_var_decl;
        next_runtime_var_index += 1;
    }
    decls.runtime_vars.items.len = next_runtime_var_index;
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
