const std = @import("std");
const declarations = @import("declarations.zig");
const gotmpl = @import("gotmpl.zig");
const parser = @import("parser.zig");
const config_mod = @import("config.zig");
const ctype_resolver = @import("ctype_resolver.zig");
const callback_render = @import("callback_render.zig");
const template_sections = @import("template_sections.zig");

const go_file_template = @embedFile("purego_gen.gotmpl");

pub const EmitKind = config_mod.EmitKind;
pub const BufferParamPair = config_mod.BufferParamPair;
pub const ExplicitBufferParamHelper = config_mod.ExplicitBufferParamHelper;
pub const PatternBufferParamHelper = config_mod.PatternBufferParamHelper;
pub const BufferParamHelper = config_mod.BufferParamHelper;
pub const ExplicitCallbackParamHelper = config_mod.ExplicitCallbackParamHelper;
pub const OwnedStringReturnHelper = config_mod.OwnedStringReturnHelper;
pub const PublicApiMatcher = config_mod.PublicApiMatcher;
pub const PublicApiOverride = config_mod.PublicApiOverride;
pub const PublicApiConfig = config_mod.PublicApiConfig;
pub const NamingConfig = config_mod.NamingConfig;
pub const ExcludeConfig = config_mod.ExcludeConfig;
pub const IncludeConfig = config_mod.IncludeConfig;
pub const GeneratorConfig = config_mod.GeneratorConfig;

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
        func.deinit(allocator);
    }
    for (src.typedefs.items) |typedef_decl| {
        if (!hasTypedefNamed(dst, typedef_decl.name)) {
            try dst.typedefs.append(allocator, typedef_decl);
            continue;
        }
        typedef_decl.deinit(allocator);
    }
    for (src.constants.items) |constant_decl| {
        if (!hasConstantNamed(dst, constant_decl.name)) {
            try dst.constants.append(allocator, constant_decl);
            continue;
        }
        constant_decl.deinit(allocator);
    }
    for (src.runtime_vars.items) |runtime_var_decl| {
        if (!hasRuntimeVarNamed(dst, runtime_var_decl.name)) {
            try dst.runtime_vars.append(allocator, runtime_var_decl);
            continue;
        }
        runtime_var_decl.deinit(allocator);
    }
    src.functions.items.len = 0;
    src.functions.deinit(allocator);
    src.typedefs.items.len = 0;
    src.typedefs.deinit(allocator);
    src.constants.items.len = 0;
    src.constants.deinit(allocator);
    src.runtime_vars.items.len = 0;
    src.runtime_vars.deinit(allocator);
    src.functions = .empty;
    src.typedefs = .empty;
    src.constants = .empty;
    src.runtime_vars = .empty;
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

const Flags = struct {
    emits_functions: bool,
    emits_types: bool,
    emits_constants: bool,
    emits_runtime_vars: bool,
    emits_struct_accessors: bool,
    has_emitted_runtime_vars: bool,
    need_purego: bool,
    need_unsafe: bool,
    need_fmt: bool,
    need_strings: bool,
    has_helper_functions: bool,
    need_union_helpers: bool,
};

fn buildFlags(config: GeneratorConfig, decls: *const declarations.CollectedDeclarations) Flags {
    const emits_functions = template_sections.containsEmitKind(config.emit, .func);
    const emits_types = template_sections.containsEmitKind(config.emit, .type);
    const emits_constants = template_sections.containsEmitKind(config.emit, .@"const");
    const emits_runtime_vars = template_sections.containsEmitKind(config.emit, .var_decl);
    const has_emitted_runtime_vars = emits_runtime_vars and decls.runtime_vars.items.len > 0;
    return .{
        .emits_functions = emits_functions,
        .emits_types = emits_types,
        .emits_constants = emits_constants,
        .emits_runtime_vars = emits_runtime_vars,
        .emits_struct_accessors = emits_types and config.struct_accessors,
        .has_emitted_runtime_vars = has_emitted_runtime_vars,
        .need_purego = emits_functions or has_emitted_runtime_vars or declarationsNeedPurego(decls),
        .need_unsafe = emits_functions or declarationsNeedUnsafe(decls) or declarationsNeedPurego(decls),
        .need_fmt = declarationsNeedFmt(emits_functions, has_emitted_runtime_vars, decls),
        .need_strings = config.owned_string_return_helpers.len > 0,
        .has_helper_functions = declarationsHaveHelperFunctions(decls),
        .need_union_helpers = declarationsNeedUnionHelpers(decls),
    };
}

fn collectCallbackParams(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_functions: bool,
) ![]callback_render.AutoCallbackParam {
    if (emits_functions and config.callback_param_helpers.len > 0)
        return callback_render.collectExplicitCallbackParams(allocator, decls, config.callback_param_helpers);
    if (config.auto_callbacks and emits_functions)
        return callback_render.collectAutoCallbackParams(allocator, decls);
    return allocator.alloc(callback_render.AutoCallbackParam, 0);
}

const Imports = struct {
    std_imports: []const []const u8,
    blank_identifiers: []const []const u8,
};

const TypeBlock = struct {
    type_block: []const []const u8,
    public_type_aliases: []const []const u8,
};

const AutoCallbackArtifacts = struct {
    type_items: []const []const u8,
    constructor_views: []const template_sections.AutoCallbackConstructorView,
};

const FunctionArtifacts = struct {
    var_texts: []const []const u8,
    register_items: []const template_sections.TemplateRegisterFunctionView,
};

const OwnedStringArtifacts = struct {
    views: []const template_sections.OwnedStringHelperView,
    gostring_name: []const u8,
};

const RuntimeVarArtifacts = struct {
    texts: []const []const u8,
    symbols: []const template_sections.TemplateRegisterFunctionView,
};

fn buildImports(
    arena: std.mem.Allocator,
    flags: Flags,
) !Imports {
    var std_imports: std.ArrayList([]const u8) = .empty;
    if (flags.need_fmt) try std_imports.append(arena, "fmt");
    if (flags.need_strings) try std_imports.append(arena, "strings");
    if (flags.need_unsafe) try std_imports.append(arena, "unsafe");

    var blank_identifiers: std.ArrayList([]const u8) = .empty;
    if (flags.need_fmt) try blank_identifiers.append(arena, "fmt.Errorf");
    if (flags.need_unsafe) try blank_identifiers.append(arena, "unsafe.Pointer(nil)");

    return .{
        .std_imports = try std_imports.toOwnedSlice(arena),
        .blank_identifiers = try blank_identifiers.toOwnedSlice(arena),
    };
}

fn buildTypeBlock(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_types: bool,
) !TypeBlock {
    var aliases: std.ArrayList([]const u8) = .empty;
    var helpers: std.ArrayList([]const u8) = .empty;
    var public_type_aliases: std.ArrayList([]const u8) = .empty;
    if (!emits_types) {
        return .{
            .type_block = try aliases.toOwnedSlice(arena),
            .public_type_aliases = try public_type_aliases.toOwnedSlice(arena),
        };
    }
    for (decls.typedefs.items) |typedef_decl| {
        try aliases.append(arena, try template_sections.renderTypeAliasItem(arena, config, typedef_decl));
        if (typedef_decl.helper_type_definition) |helper_type_definition| {
            try helpers.append(arena, helper_type_definition);
        }
        if (!ctype_resolver.matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) continue;
        const public_name = try ctype_resolver.renderPublicApiName(
            arena,
            config.public_api.strip_prefix,
            config.public_api.type_aliases_overrides,
            typedef_decl.name,
        );
        const emitted_internal_name = try ctype_resolver.renderTypeName(arena, config, typedef_decl.name);
        try public_type_aliases.append(arena, try std.fmt.allocPrint(arena, "\t{s} = {s}\n", .{ public_name, emitted_internal_name }));
    }
    // Preserve the original layout: all aliases first, then all helper type definitions.
    for (helpers.items) |item| try aliases.append(arena, item);
    return .{
        .type_block = try aliases.toOwnedSlice(arena),
        .public_type_aliases = try public_type_aliases.toOwnedSlice(arena),
    };
}

fn buildAutoCallbackArtifacts(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    callback_params: []const callback_render.AutoCallbackParam,
) !AutoCallbackArtifacts {
    var type_items: std.ArrayList([]const u8) = .empty;
    var emitted_type_names: std.ArrayList([]const u8) = .empty;
    for (callback_params) |auto_callback| {
        const func = decls.functions.items[auto_callback.function_index];
        const param_c_type = func.parameter_c_types[auto_callback.parameter_index];
        if (ctype_resolver.underlyingTypedefCType(decls, param_c_type)) |underlying| {
            if (ctype_resolver.isFunctionPointerCType(underlying)) continue;
        }
        const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, auto_callback);
        const emitted_helper_type_name = try ctype_resolver.renderTypeName(arena, config, helper_type_name);
        if (ctype_resolver.containsString(emitted_type_names.items, emitted_helper_type_name)) continue;
        try type_items.append(arena, try template_sections.renderAutoCallbackTypeItem(arena, config, decls, callback_params, auto_callback));
        try emitted_type_names.append(arena, emitted_helper_type_name);
    }

    var constructor_views: std.ArrayList(template_sections.AutoCallbackConstructorView) = .empty;
    var emitted_constructor_names: std.ArrayList([]const u8) = .empty;
    for (callback_params) |auto_callback| {
        const func = decls.functions.items[auto_callback.function_index];
        const param_c_type = func.parameter_c_types[auto_callback.parameter_index];
        if (ctype_resolver.underlyingTypedefCType(decls, param_c_type)) |underlying| {
            if (ctype_resolver.isFunctionPointerCType(underlying)) continue;
        }
        const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, auto_callback);
        const emitted_helper_type_name = try ctype_resolver.renderTypeName(arena, config, helper_type_name);
        const constructor_name = try callback_render.renderEffectiveCallbackConstructorName(arena, decls, callback_params, auto_callback);
        const emitted_constructor_name = try ctype_resolver.renderFuncName(arena, config, constructor_name);
        if (ctype_resolver.containsString(emitted_constructor_names.items, emitted_constructor_name)) continue;
        try constructor_views.append(arena, .{
            .constructor_name = emitted_constructor_name,
            .type_name = emitted_helper_type_name,
        });
        try emitted_constructor_names.append(arena, emitted_constructor_name);
    }
    return .{
        .type_items = try type_items.toOwnedSlice(arena),
        .constructor_views = try constructor_views.toOwnedSlice(arena),
    };
}

fn buildConstantViews(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_constants: bool,
) ![]const template_sections.ConstantItemView {
    var views: std.ArrayList(template_sections.ConstantItemView) = .empty;
    if (!emits_constants) return views.toOwnedSlice(arena);
    for (decls.constants.items) |constant_decl| {
        var comment_aw: std.Io.Writer.Allocating = .init(arena);
        const cw = &comment_aw.writer;
        try template_sections.writeComment(cw, "\t", constant_decl.comment);
        const comment_str = try comment_aw.toOwnedSlice();
        const emitted_name = try ctype_resolver.renderConstName(arena, config, constant_decl.name);
        const typed_prefix = if (config.typed_sentinel_constants and constant_decl.typed_go_type != null)
            try std.fmt.allocPrint(arena, " {s}", .{constant_decl.typed_go_type.?})
        else
            try arena.dupe(u8, "");
        try views.append(arena, .{
            .comment = comment_str,
            .name = emitted_name,
            .typed_prefix = typed_prefix,
            .value_expr = constant_decl.value_expr,
        });
    }
    return views.toOwnedSlice(arena);
}

fn buildStructAccessorViews(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_struct_accessors: bool,
) ![]const template_sections.StructAccessorView {
    var views: std.ArrayList(template_sections.StructAccessorView) = .empty;
    if (!emits_struct_accessors) return views.toOwnedSlice(arena);
    for ([_]bool{ false, true }) |emit_union_fields| {
        for (decls.typedefs.items) |typedef_decl| {
            const type_name = try ctype_resolver.renderTypeName(arena, config, typedef_decl.name);
            for (typedef_decl.accessor_fields) |field| {
                if (field.is_union != emit_union_fields) continue;
                const getter_base = try std.fmt.allocPrint(arena, "Get_{s}", .{field.name});
                const getter_name = try ctype_resolver.renderFuncName(arena, config, getter_base);
                const setter_base = try std.fmt.allocPrint(arena, "Set_{s}", .{field.name});
                const setter_name = try ctype_resolver.renderFuncName(arena, config, setter_base);
                try views.append(arena, .{
                    .type_name = type_name,
                    .getter_name = getter_name,
                    .setter_name = setter_name,
                    .field_name = field.name,
                    .go_type = field.go_type,
                    .is_union = field.is_union,
                });
            }
        }
    }
    return views.toOwnedSlice(arena);
}

fn buildHelperTexts(
    arena: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]const []const u8 {
    var helpers: std.ArrayList([]const u8) = .empty;
    for (decls.typedefs.items) |typedef_decl| {
        if (typedef_decl.helper_function_definition) |text| {
            try helpers.append(arena, try std.fmt.allocPrint(arena, "{s}\n", .{text}));
        }
    }
    return helpers.toOwnedSlice(arena);
}

fn buildPublicWrapperViews(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_types: bool,
) ![]const template_sections.PublicWrapperView {
    var views: std.ArrayList(template_sections.PublicWrapperView) = .empty;
    for (decls.functions.items) |func| {
        if (!ctype_resolver.matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_include)) continue;
        if (ctype_resolver.matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_exclude)) continue;
        const public_name = try ctype_resolver.renderPublicApiName(arena, config.public_api.strip_prefix, config.public_api.wrappers_overrides, func.name);
        const target_name = try ctype_resolver.renderFuncName(arena, config, func.name);
        const result_type = try callback_render.resolvePublicApiGoType(arena, config, decls, func.result_c_type, emits_types);
        var params: std.ArrayList(template_sections.PublicWrapperParamView) = .empty;
        for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
            const go_type = try callback_render.resolvePublicApiGoType(arena, config, decls, param_c_type, emits_types);
            try params.append(arena, .{ .name = param_name, .go_type = go_type });
        }
        try views.append(arena, .{
            .public_name = public_name,
            .target_name = target_name,
            .params = try params.toOwnedSlice(arena),
            .result_type = result_type,
        });
    }
    return views.toOwnedSlice(arena);
}

fn buildFunctionVarsAndRegisters(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    callback_params: []const callback_render.AutoCallbackParam,
) !FunctionArtifacts {
    var var_items: std.ArrayList([]const u8) = .empty;
    var register_items: std.ArrayList(template_sections.TemplateRegisterFunctionView) = .empty;
    for (decls.functions.items, 0..) |func, function_index| {
        try var_items.append(arena, try template_sections.renderFunctionVarItem(arena, config, decls, func, function_index, callback_params));
        const emitted_func_name = try ctype_resolver.renderFuncName(arena, config, func.name);
        try register_items.append(arena, .{ .name = emitted_func_name, .symbol = func.name });
    }
    return .{
        .var_texts = try var_items.toOwnedSlice(arena),
        .register_items = try register_items.toOwnedSlice(arena),
    };
}

fn buildBufferHelperTexts(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
) ![]const []const u8 {
    var items: std.ArrayList([]const u8) = .empty;
    var explicit_names: std.ArrayList([]const u8) = .empty;
    for (config.buffer_param_helpers) |helper| switch (helper) {
        .explicit => |explicit| try explicit_names.append(arena, explicit.function_name),
        .pattern => {},
    };
    var emitted_names: std.ArrayList([]const u8) = .empty;
    for (config.buffer_param_helpers) |helper| switch (helper) {
        .explicit => |explicit| {
            const func = ctype_resolver.findFunctionByName(decls, explicit.function_name) orelse return error.BufferHelperTargetFunctionNotFound;
            const pairs = try template_sections.resolveExplicitBufferPairs(arena, func, explicit.pairs);
            try items.append(arena, try template_sections.renderBufferHelperItem(arena, config, func, pairs));
            try emitted_names.append(arena, func.name);
        },
        .pattern => |pattern| {
            const indices = try arena.alloc(usize, decls.functions.items.len);
            for (indices, 0..) |*slot, index| slot.* = index;
            ctype_resolver.sortFunctionIndicesByName(indices, decls.functions.items);

            var match_count: usize = 0;
            for (indices) |index| {
                const func = decls.functions.items[index];
                if (ctype_resolver.containsString(explicit_names.items, func.name)) continue;
                if (ctype_resolver.containsString(emitted_names.items, func.name)) continue;
                if (!ctype_resolver.functionNameMatchesPattern(func.name, pattern.function_pattern)) continue;
                const pairs = try template_sections.detectBufferPairs(arena, func);
                if (pairs.len == 0) continue;
                try items.append(arena, try template_sections.renderBufferHelperItem(arena, config, func, pairs));
                try emitted_names.append(arena, func.name);
                match_count += 1;
            }
            if (match_count == 0) return error.BufferPatternMatchedNoFunctions;
        },
    };
    return items.toOwnedSlice(arena);
}

fn buildAutoCallbackWrapperViews(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    callback_params: []const callback_render.AutoCallbackParam,
    emits_types: bool,
) ![]const template_sections.AutoCallbackWrapperView {
    var views: std.ArrayList(template_sections.AutoCallbackWrapperView) = .empty;
    for (decls.functions.items, 0..) |func, function_index| {
        if (!callback_render.hasAutoCallbackParamForFunction(callback_params, function_index)) continue;
        const wrapper_name_base = try std.fmt.allocPrint(arena, "{s}_callbacks", .{func.name});
        const wrapper_name = try ctype_resolver.renderFuncName(arena, config, wrapper_name_base);
        const target_name = try ctype_resolver.renderFuncName(arena, config, func.name);
        const result_mapped = try callback_render.resolveFunctionParameterType(arena, decls, func.result_c_type, false, emits_types, config.strict_enum_typedefs);
        var params: std.ArrayList(template_sections.AutoCallbackWrapperParamView) = .empty;
        for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
            if (callback_render.isAutoCallbackParameter(callback_params, function_index, parameter_index)) {
                if (ctype_resolver.underlyingTypedefCType(decls, param_c_type)) |underlying| {
                    if (ctype_resolver.isFunctionPointerCType(underlying)) {
                        const inline_sig = try callback_render.renderCallbackGoSignature(arena, decls, underlying);
                        try params.append(arena, .{ .name = param_name, .go_type = inline_sig, .is_callback = true });
                        continue;
                    }
                }
                const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, .{
                    .function_index = function_index,
                    .parameter_index = parameter_index,
                });
                const emitted_type = try ctype_resolver.renderTypeName(arena, config, helper_type_name);
                try params.append(arena, .{ .name = param_name, .go_type = emitted_type, .is_callback = true });
            } else {
                const mapped = try callback_render.resolveFunctionParameterType(arena, decls, param_c_type, false, emits_types, config.strict_enum_typedefs);
                try params.append(arena, .{ .name = param_name, .go_type = mapped.go_type, .is_callback = false });
            }
        }
        try views.append(arena, .{
            .wrapper_name = wrapper_name,
            .target_name = target_name,
            .params = try params.toOwnedSlice(arena),
            .result_type = result_mapped.go_type,
        });
    }
    return views.toOwnedSlice(arena);
}

fn buildOwnedStringHelpers(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_types: bool,
) !OwnedStringArtifacts {
    var views: std.ArrayList(template_sections.OwnedStringHelperView) = .empty;
    for (config.owned_string_return_helpers) |helper| {
        const func = ctype_resolver.findFunctionByName(decls, helper.function_name) orelse return error.OwnedStringHelperTargetFunctionNotFound;
        _ = ctype_resolver.findFunctionByName(decls, helper.free_func_name) orelse return error.OwnedStringHelperFreeFunctionNotFound;
        const helper_base = try std.fmt.allocPrint(arena, "{s}_string", .{func.name});
        const helper_name = try ctype_resolver.renderFuncName(arena, config, helper_base);
        const target_name = try ctype_resolver.renderFuncName(arena, config, func.name);
        const free_name = try ctype_resolver.renderFuncName(arena, config, helper.free_func_name);
        const gostring_n = try ctype_resolver.renderFuncName(arena, config, "gostring");
        var params: std.ArrayList(template_sections.OwnedStringHelperParamView) = .empty;
        for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
            const mapped = try callback_render.resolveFunctionParameterType(arena, decls, param_c_type, false, emits_types, config.strict_enum_typedefs);
            try params.append(arena, .{
                .name = param_name,
                .go_type = mapped.go_type,
                .c_comment = mapped.comment orelse "",
            });
        }
        try views.append(arena, .{
            .helper_name = helper_name,
            .target_name = target_name,
            .free_name = free_name,
            .gostring_name = gostring_n,
            .params = try params.toOwnedSlice(arena),
        });
    }
    const gostring_name = if (config.owned_string_return_helpers.len > 0)
        try ctype_resolver.renderFuncName(arena, config, "gostring")
    else
        "";
    return .{ .views = try views.toOwnedSlice(arena), .gostring_name = gostring_name };
}

fn buildRuntimeVarSection(
    arena: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    emits_runtime_vars: bool,
) !RuntimeVarArtifacts {
    var texts: std.ArrayList([]const u8) = .empty;
    var symbols: std.ArrayList(template_sections.TemplateRegisterFunctionView) = .empty;
    if (!emits_runtime_vars) return .{
        .texts = try texts.toOwnedSlice(arena),
        .symbols = try symbols.toOwnedSlice(arena),
    };
    for (decls.runtime_vars.items) |runtime_var_decl| {
        var aw: std.Io.Writer.Allocating = .init(arena);
        const w = &aw.writer;
        try template_sections.writeComment(w, "\t", runtime_var_decl.comment);
        const emitted_var_name = try ctype_resolver.renderRuntimeVarName(arena, config, runtime_var_decl.name);
        try w.print("\t{s} uintptr\n", .{emitted_var_name});
        try texts.append(arena, try aw.toOwnedSlice());
        try symbols.append(arena, .{ .name = emitted_var_name, .symbol = runtime_var_decl.name });
    }
    return .{
        .texts = try texts.toOwnedSlice(arena),
        .symbols = try symbols.toOwnedSlice(arena),
    };
}

const SectionInputs = struct {
    flags: Flags,
    type_block: []const []const u8,
    public_type_aliases: []const []const u8,
    auto_callback_type_items: []const []const u8,
    auto_callback_constructor_views: []const template_sections.AutoCallbackConstructorView,
    constant_views: []const template_sections.ConstantItemView,
    struct_accessor_views: []const template_sections.StructAccessorView,
    helper_texts: []const []const u8,
    public_wrapper_views: []const template_sections.PublicWrapperView,
    function_var_texts: []const []const u8,
    buffer_helper_texts: []const []const u8,
    auto_callback_wrapper_views: []const template_sections.AutoCallbackWrapperView,
    owned_string_helper_views: []const template_sections.OwnedStringHelperView,
    gostring_name: []const u8,
    register_function_items: []const template_sections.TemplateRegisterFunctionView,
    register_functions_name: []const u8,
    runtime_var_texts: []const []const u8,
    runtime_var_symbols: []const template_sections.TemplateRegisterFunctionView,
    load_runtime_vars_name: []const u8,
};

fn assembleSections(
    arena: std.mem.Allocator,
    inputs: SectionInputs,
) ![]const template_sections.TemplateSectionView {
    var sections: std.ArrayList(template_sections.TemplateSectionView) = .empty;
    var has_emitted_section = false;
    try appendBlock(arena, &sections, &has_emitted_section, "type_block", inputs.type_block, false, true);
    try appendBlock(arena, &sections, &has_emitted_section, "type_block", inputs.public_type_aliases, false, false);
    try appendBlock(arena, &sections, &has_emitted_section, "type_block", inputs.auto_callback_type_items, false, false);
    if (inputs.auto_callback_constructor_views.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "auto_callback_constructors",
            .gap = template_sections.sectionGap(has_emitted_section, false),
            .auto_callback_constructor_items = inputs.auto_callback_constructor_views,
        });
    }
    if (inputs.flags.emits_constants and !inputs.flags.has_helper_functions and inputs.constant_views.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "const_block",
            .gap = template_sections.sectionGap(has_emitted_section, true),
            .const_items = inputs.constant_views,
        });
    }
    try appendText(arena, &sections, &has_emitted_section, inputs.helper_texts, false);
    if (inputs.flags.need_union_helpers) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "union_helpers",
            .gap = template_sections.sectionGap(has_emitted_section, false),
        });
    }
    if (inputs.struct_accessor_views.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "struct_accessors",
            .gap = template_sections.sectionGap(has_emitted_section, false),
            .struct_accessor_items = inputs.struct_accessor_views,
        });
    }
    if (inputs.flags.emits_constants and inputs.flags.has_helper_functions and inputs.constant_views.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "const_block",
            .gap = template_sections.sectionGap(has_emitted_section, true),
            .const_items = inputs.constant_views,
        });
    }
    if (inputs.public_wrapper_views.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "public_wrappers",
            .gap = template_sections.sectionGap(has_emitted_section, true),
            .public_wrapper_items = inputs.public_wrapper_views,
        });
    }
    try appendBlock(arena, &sections, &has_emitted_section, "var_block", inputs.function_var_texts, inputs.flags.emits_functions, true);
    try appendText(arena, &sections, &has_emitted_section, inputs.buffer_helper_texts, false);
    if (inputs.auto_callback_wrapper_views.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "auto_callback_wrappers",
            .gap = template_sections.sectionGap(has_emitted_section, false),
            .auto_callback_wrapper_items = inputs.auto_callback_wrapper_views,
        });
    }
    if (inputs.owned_string_helper_views.len > 0 or inputs.gostring_name.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "owned_string_helpers",
            .gap = template_sections.sectionGap(has_emitted_section, false),
            .owned_string_helper_items = inputs.owned_string_helper_views,
            .gostring_name = inputs.gostring_name,
        });
    }
    if (inputs.register_function_items.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "register_functions",
            .gap = template_sections.sectionGap(has_emitted_section, true),
            .register_functions_name = inputs.register_functions_name,
            .register_function_items = inputs.register_function_items,
        });
    }
    try appendBlock(arena, &sections, &has_emitted_section, "var_block", inputs.runtime_var_texts, inputs.flags.has_emitted_runtime_vars, true);
    if (inputs.load_runtime_vars_name.len > 0) {
        try template_sections.appendSection(arena, &sections, &has_emitted_section, .{
            .kind = "runtime_var_loader",
            .gap = template_sections.sectionGap(has_emitted_section, true),
            .load_runtime_vars_name = inputs.load_runtime_vars_name,
            .runtime_var_symbol_items = inputs.runtime_var_symbols,
        });
    }
    return sections.toOwnedSlice(arena);
}

pub fn generateGoSource(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    skip_gofmt: bool,
) ![]u8 {
    const flags = buildFlags(config, decls);

    const callback_params = try collectCallbackParams(allocator, config, decls, flags.emits_functions);
    defer allocator.free(callback_params);

    var arena_state = std.heap.ArenaAllocator.init(allocator);
    defer arena_state.deinit();
    const arena = arena_state.allocator();

    const imports = try buildImports(arena, flags);
    const type_block = try buildTypeBlock(arena, config, decls, flags.emits_types);
    const auto_callback_artifacts = try buildAutoCallbackArtifacts(arena, config, decls, callback_params);
    const constant_views = try buildConstantViews(arena, config, decls, flags.emits_constants);
    const struct_accessor_views = try buildStructAccessorViews(arena, config, decls, flags.emits_struct_accessors);
    const helper_texts = try buildHelperTexts(arena, decls);

    const public_wrapper_views: []const template_sections.PublicWrapperView = if (flags.emits_functions)
        try buildPublicWrapperViews(arena, config, decls, flags.emits_types)
    else
        &.{};
    const fn_artifacts: FunctionArtifacts = if (flags.emits_functions)
        try buildFunctionVarsAndRegisters(arena, config, decls, callback_params)
    else
        .{ .var_texts = &.{}, .register_items = &.{} };
    const buffer_helper_texts: []const []const u8 = if (flags.emits_functions)
        try buildBufferHelperTexts(arena, config, decls)
    else
        &.{};
    const auto_callback_wrapper_views: []const template_sections.AutoCallbackWrapperView = if (flags.emits_functions)
        try buildAutoCallbackWrapperViews(arena, config, decls, callback_params, flags.emits_types)
    else
        &.{};
    const owned_string: OwnedStringArtifacts = if (flags.emits_functions)
        try buildOwnedStringHelpers(arena, config, decls, flags.emits_types)
    else
        .{ .views = &.{}, .gostring_name = "" };

    const runtime = try buildRuntimeVarSection(arena, config, decls, flags.emits_runtime_vars);

    const register_functions_name = if (flags.emits_functions)
        try ctype_resolver.renderFuncName(arena, config, try std.fmt.allocPrint(arena, "{s}_register_functions", .{config.lib_id}))
    else
        "";
    const load_runtime_vars_name = if (flags.has_emitted_runtime_vars)
        try ctype_resolver.renderFuncName(arena, config, try std.fmt.allocPrint(arena, "{s}_load_runtime_vars", .{config.lib_id}))
    else
        "";

    const section_items = try assembleSections(arena, .{
        .flags = flags,
        .type_block = type_block.type_block,
        .public_type_aliases = type_block.public_type_aliases,
        .auto_callback_type_items = auto_callback_artifacts.type_items,
        .auto_callback_constructor_views = auto_callback_artifacts.constructor_views,
        .constant_views = constant_views,
        .struct_accessor_views = struct_accessor_views,
        .helper_texts = helper_texts,
        .public_wrapper_views = public_wrapper_views,
        .function_var_texts = fn_artifacts.var_texts,
        .buffer_helper_texts = buffer_helper_texts,
        .auto_callback_wrapper_views = auto_callback_wrapper_views,
        .owned_string_helper_views = owned_string.views,
        .gostring_name = owned_string.gostring_name,
        .register_function_items = fn_artifacts.register_items,
        .register_functions_name = register_functions_name,
        .runtime_var_texts = runtime.texts,
        .runtime_var_symbols = runtime.symbols,
        .load_runtime_vars_name = load_runtime_vars_name,
    });

    const template_data = .{
        .package_name = config.package_name,
        .has_import_block = imports.std_imports.len > 0 or flags.need_purego,
        .std_imports = imports.std_imports,
        .has_purego_import = flags.need_purego,
        .has_blank_identifier_block = imports.blank_identifiers.len > 0,
        .blank_identifiers = imports.blank_identifiers,
        .sections = section_items,
    };

    var aw: std.Io.Writer.Allocating = .init(allocator);
    errdefer aw.deinit();
    try gotmpl.render(&aw.writer, go_file_template, template_data);

    const rendered = try aw.toOwnedSlice();
    if (skip_gofmt) {
        return rendered;
    }
    defer allocator.free(rendered);
    return template_sections.formatGoSource(allocator, rendered);
}

pub fn applyExcludeFilters(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *declarations.CollectedDeclarations,
) void {
    filterInPlace(declarations.FunctionDecl, allocator, &decls.functions, config.exclude.func_name, .exclude);
    filterInPlace(declarations.TypedefDecl, allocator, &decls.typedefs, config.exclude.type_name, .exclude);
    filterInPlace(declarations.ConstantDecl, allocator, &decls.constants, config.exclude.const_name, .exclude);
    filterInPlace(declarations.RuntimeVarDecl, allocator, &decls.runtime_vars, config.exclude.var_name, .exclude);
}

pub fn applyIncludeFilters(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *declarations.CollectedDeclarations,
) void {
    filterInPlace(declarations.FunctionDecl, allocator, &decls.functions, config.include.func_name, .include);
    filterInPlace(declarations.TypedefDecl, allocator, &decls.typedefs, config.include.type_name, .include);
    filterInPlace(declarations.ConstantDecl, allocator, &decls.constants, config.include.const_name, .include);
    filterInPlace(declarations.RuntimeVarDecl, allocator, &decls.runtime_vars, config.include.var_name, .include);
}

fn appendBlock(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(template_sections.TemplateSectionView),
    has_emitted_section: *bool,
    kind: []const u8,
    block_items: []const []const u8,
    force_block: bool,
    add_leading_gap: bool,
) !void {
    if (!force_block and block_items.len == 0) return;
    try template_sections.appendSection(allocator, sections, has_emitted_section, .{
        .kind = kind,
        .gap = template_sections.sectionGap(has_emitted_section.*, add_leading_gap),
        .block_items = block_items,
        .text_items = &.{},
    });
}

fn appendText(
    allocator: std.mem.Allocator,
    sections: *std.ArrayList(template_sections.TemplateSectionView),
    has_emitted_section: *bool,
    text_items: []const []const u8,
    add_leading_gap: bool,
) !void {
    if (text_items.len == 0) return;
    try template_sections.appendSection(allocator, sections, has_emitted_section, .{
        .kind = "text",
        .gap = template_sections.sectionGap(has_emitted_section.*, add_leading_gap),
        .block_items = &.{},
        .text_items = text_items,
    });
}

const FilterMode = enum { include, exclude };

fn filterInPlace(
    comptime Decl: type,
    allocator: std.mem.Allocator,
    list: *std.ArrayListUnmanaged(Decl),
    pattern: []const u8,
    mode: FilterMode,
) void {
    var next: usize = 0;
    for (list.items) |decl| {
        const matched = switch (mode) {
            .exclude => ctype_resolver.isExactExcluded(pattern, decl.name),
            .include => !ctype_resolver.isIncludedOnly(pattern, decl.name),
        };
        if (matched) {
            decl.deinit(allocator);
            continue;
        }
        list.items[next] = decl;
        next += 1;
    }
    list.items.len = next;
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
