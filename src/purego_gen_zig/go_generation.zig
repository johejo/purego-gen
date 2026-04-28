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
    src.functions = .empty;
    src.typedefs = .empty;
    src.constants = .empty;
    src.runtime_vars = .empty;
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

pub fn generateGoSource(
    allocator: std.mem.Allocator,
    config: GeneratorConfig,
    decls: *const declarations.CollectedDeclarations,
    skip_gofmt: bool,
) ![]u8 {
    const emits_functions = template_sections.containsEmitKind(config.emit, .func);
    const emits_types = template_sections.containsEmitKind(config.emit, .type);
    const emits_constants = template_sections.containsEmitKind(config.emit, .@"const");
    const emits_runtime_vars = template_sections.containsEmitKind(config.emit, .var_decl);
    const emits_struct_accessors = emits_types and config.struct_accessors;
    const has_emitted_runtime_vars = emits_runtime_vars and decls.runtime_vars.items.len > 0;

    const need_purego = emits_functions or has_emitted_runtime_vars or declarationsNeedPurego(decls);
    const need_unsafe = emits_functions or declarationsNeedUnsafe(decls) or declarationsNeedPurego(decls);
    const need_fmt = declarationsNeedFmt(emits_functions, has_emitted_runtime_vars, decls);
    const need_strings = config.owned_string_return_helpers.len > 0;
    const has_helper_functions = declarationsHaveHelperFunctions(decls);
    const callback_params = if (emits_functions and config.callback_param_helpers.len > 0)
        try callback_render.collectExplicitCallbackParams(allocator, decls, config.callback_param_helpers)
    else if (config.auto_callbacks and emits_functions)
        try callback_render.collectAutoCallbackParams(allocator, decls)
    else
        try allocator.alloc(callback_render.AutoCallbackParam, 0);
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
            try type_alias_items.append(arena, try template_sections.renderTypeAliasItem(arena, config, typedef_decl));
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
            if (!ctype_resolver.matchesAnyPublicApiMatcher(typedef_decl.name, config.public_api.type_aliases_include)) continue;
            const public_name = try ctype_resolver.renderPublicApiName(
                arena,
                config.public_api.strip_prefix,
                config.public_api.type_aliases_overrides,
                typedef_decl.name,
            );
            const emitted_internal_name = try ctype_resolver.renderTypeName(arena, config, typedef_decl.name);
            try public_type_alias_items.append(arena, try std.fmt.allocPrint(arena, "\t{s} = {s}\n", .{ public_name, emitted_internal_name }));
        }
    }
    const public_type_alias_texts = try public_type_alias_items.toOwnedSlice(arena);

    var auto_callback_type_items: std.ArrayList([]const u8) = .empty;
    var emitted_callback_type_names: std.ArrayList([]const u8) = .empty;
    if (callback_params.len > 0) {
        for (callback_params) |auto_callback| {
            const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, auto_callback);
            const emitted_helper_type_name = try ctype_resolver.renderTypeName(arena, config, helper_type_name);
            if (ctype_resolver.containsString(emitted_callback_type_names.items, emitted_helper_type_name)) continue;
            try auto_callback_type_items.append(arena, try template_sections.renderAutoCallbackTypeItem(arena, config, decls, callback_params, auto_callback));
            try emitted_callback_type_names.append(arena, emitted_helper_type_name);
        }
    }
    const auto_callback_type_texts = try auto_callback_type_items.toOwnedSlice(arena);

    var auto_callback_constructor_views: std.ArrayList(template_sections.AutoCallbackConstructorView) = .empty;
    var emitted_callback_constructor_names: std.ArrayList([]const u8) = .empty;
    if (callback_params.len > 0) {
        for (callback_params) |auto_callback| {
            const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, auto_callback);
            const emitted_helper_type_name = try ctype_resolver.renderTypeName(arena, config, helper_type_name);
            const constructor_name = try callback_render.renderEffectiveCallbackConstructorName(arena, decls, callback_params, auto_callback);
            const emitted_constructor_name = try ctype_resolver.renderFuncName(arena, config, constructor_name);
            if (ctype_resolver.containsString(emitted_callback_constructor_names.items, emitted_constructor_name)) continue;
            try auto_callback_constructor_views.append(arena, .{
                .constructor_name = emitted_constructor_name,
                .type_name = emitted_helper_type_name,
            });
            try emitted_callback_constructor_names.append(arena, emitted_constructor_name);
        }
    }
    const auto_callback_constructor_view_items = try auto_callback_constructor_views.toOwnedSlice(arena);

    var constant_views: std.ArrayList(template_sections.ConstantItemView) = .empty;
    if (emits_constants) {
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
            try constant_views.append(arena, .{
                .comment = comment_str,
                .name = emitted_name,
                .typed_prefix = typed_prefix,
                .value_expr = constant_decl.value_expr,
            });
        }
    }
    const constant_view_items = try constant_views.toOwnedSlice(arena);

    var struct_accessor_views: std.ArrayList(template_sections.StructAccessorView) = .empty;
    if (emits_struct_accessors) {
        for ([_]bool{ false, true }) |emit_union_fields| {
            for (decls.typedefs.items) |typedef_decl| {
                const type_name = try ctype_resolver.renderTypeName(arena, config, typedef_decl.name);
                for (typedef_decl.accessor_fields) |field| {
                    if (field.is_union != emit_union_fields) continue;
                    const getter_base = try std.fmt.allocPrint(arena, "Get_{s}", .{field.name});
                    const getter_name = try ctype_resolver.renderFuncName(arena, config, getter_base);
                    const setter_base = try std.fmt.allocPrint(arena, "Set_{s}", .{field.name});
                    const setter_name = try ctype_resolver.renderFuncName(arena, config, setter_base);
                    try struct_accessor_views.append(arena, .{
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

    var public_wrapper_views: std.ArrayList(template_sections.PublicWrapperView) = .empty;
    var function_var_items: std.ArrayList([]const u8) = .empty;
    var buffer_helper_items: std.ArrayList([]const u8) = .empty;
    var auto_callback_wrapper_views: std.ArrayList(template_sections.AutoCallbackWrapperView) = .empty;
    var owned_string_helper_views: std.ArrayList(template_sections.OwnedStringHelperView) = .empty;
    var gostring_name_str: []const u8 = "";
    var register_functions: std.ArrayList(template_sections.TemplateRegisterFunctionView) = .empty;

    if (emits_functions) {
        for (decls.functions.items) |func| {
            if (ctype_resolver.matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_include) and
                !ctype_resolver.matchesAnyPublicApiMatcher(func.name, config.public_api.wrappers_exclude))
            {
                const public_name = try ctype_resolver.renderPublicApiName(arena, config.public_api.strip_prefix, config.public_api.wrappers_overrides, func.name);
                const target_name = try ctype_resolver.renderFuncName(arena, config, func.name);
                const result_type = try callback_render.resolvePublicApiGoType(arena, config, decls, func.result_c_type, template_sections.containsEmitKind(config.emit, .type));
                var params: std.ArrayList(template_sections.PublicWrapperParamView) = .empty;
                for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
                    const go_type = try callback_render.resolvePublicApiGoType(arena, config, decls, param_c_type, template_sections.containsEmitKind(config.emit, .type));
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
            try function_var_items.append(arena, try template_sections.renderFunctionVarItem(arena, config, decls, func, function_index, callback_params));
            const emitted_func_name = try ctype_resolver.renderFuncName(arena, config, func.name);
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
                    const func = ctype_resolver.findFunctionByName(decls, explicit.function_name) orelse return error.BufferHelperTargetFunctionNotFound;
                    const pairs = try template_sections.resolveExplicitBufferPairs(arena, func, explicit.pairs);
                    try buffer_helper_items.append(arena, try template_sections.renderBufferHelperItem(arena, config, func, pairs));
                    try emitted_buffer_names.append(arena, func.name);
                },
                .pattern => |pattern| {
                    const function_count = decls.functions.items.len;
                    const indices = try arena.alloc(usize, function_count);
                    for (indices, 0..) |*slot, index| slot.* = index;
                    ctype_resolver.sortFunctionIndicesByName(indices, decls.functions.items);

                    var match_count: usize = 0;
                    for (indices) |index| {
                        const func = decls.functions.items[index];
                        if (ctype_resolver.containsString(explicit_names.items, func.name)) continue;
                        if (ctype_resolver.containsString(emitted_buffer_names.items, func.name)) continue;
                        if (!ctype_resolver.functionNameMatchesPattern(func.name, pattern.function_pattern)) continue;
                        const pairs = try template_sections.detectBufferPairs(arena, func);
                        if (pairs.len == 0) continue;
                        try buffer_helper_items.append(arena, try template_sections.renderBufferHelperItem(arena, config, func, pairs));
                        try emitted_buffer_names.append(arena, func.name);
                        match_count += 1;
                    }
                    if (match_count == 0) return error.BufferPatternMatchedNoFunctions;
                },
            }
        }

        for (decls.functions.items, 0..) |func, function_index| {
            if (!callback_render.hasAutoCallbackParamForFunction(callback_params, function_index)) continue;
            const wrapper_name_base = try std.fmt.allocPrint(arena, "{s}_callbacks", .{func.name});
            const wrapper_name = try ctype_resolver.renderFuncName(arena, config, wrapper_name_base);
            const target_name = try ctype_resolver.renderFuncName(arena, config, func.name);
            const result_mapped = try callback_render.resolveFunctionParameterType(arena, decls, func.result_c_type, false, template_sections.containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
            var params: std.ArrayList(template_sections.AutoCallbackWrapperParamView) = .empty;
            for (func.parameter_names, func.parameter_c_types, 0..) |param_name, param_c_type, parameter_index| {
                if (callback_render.isAutoCallbackParameter(callback_params, function_index, parameter_index)) {
                    const helper_type_name = try callback_render.renderEffectiveCallbackFuncTypeName(arena, decls, callback_params, .{
                        .function_index = function_index,
                        .parameter_index = parameter_index,
                    });
                    const emitted_type = try ctype_resolver.renderTypeName(arena, config, helper_type_name);
                    try params.append(arena, .{ .name = param_name, .go_type = emitted_type, .is_callback = true });
                } else {
                    const mapped = try callback_render.resolveFunctionParameterType(arena, decls, param_c_type, false, template_sections.containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
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
            const func = ctype_resolver.findFunctionByName(decls, helper.function_name) orelse return error.OwnedStringHelperTargetFunctionNotFound;
            _ = ctype_resolver.findFunctionByName(decls, helper.free_func_name) orelse return error.OwnedStringHelperFreeFunctionNotFound;
            const helper_base = try std.fmt.allocPrint(arena, "{s}_string", .{func.name});
            const helper_name = try ctype_resolver.renderFuncName(arena, config, helper_base);
            const target_name = try ctype_resolver.renderFuncName(arena, config, func.name);
            const free_name = try ctype_resolver.renderFuncName(arena, config, helper.free_func_name);
            const gostring_n = try ctype_resolver.renderFuncName(arena, config, "gostring");
            var params: std.ArrayList(template_sections.OwnedStringHelperParamView) = .empty;
            for (func.parameter_names, func.parameter_c_types) |param_name, param_c_type| {
                const mapped = try callback_render.resolveFunctionParameterType(arena, decls, param_c_type, false, template_sections.containsEmitKind(config.emit, .type), config.strict_enum_typedefs);
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
            gostring_name_str = try ctype_resolver.renderFuncName(arena, config, "gostring");
        }
    }
    const public_wrapper_view_items = try public_wrapper_views.toOwnedSlice(arena);
    const function_var_texts = try function_var_items.toOwnedSlice(arena);
    const buffer_helper_texts = try buffer_helper_items.toOwnedSlice(arena);
    const auto_callback_wrapper_view_items = try auto_callback_wrapper_views.toOwnedSlice(arena);
    const owned_string_helper_view_items = try owned_string_helper_views.toOwnedSlice(arena);
    const register_function_items = try register_functions.toOwnedSlice(arena);

    var runtime_var_items: std.ArrayList([]const u8) = .empty;
    var runtime_var_symbols: std.ArrayList(template_sections.TemplateRegisterFunctionView) = .empty;
    if (emits_runtime_vars) {
        for (decls.runtime_vars.items) |runtime_var_decl| {
            var aw: std.Io.Writer.Allocating = .init(arena);
            const w = &aw.writer;
            try template_sections.writeComment(w, "\t", runtime_var_decl.comment);
            const emitted_var_name = try ctype_resolver.renderRuntimeVarName(arena, config, runtime_var_decl.name);
            try w.print("\t{s} uintptr\n", .{emitted_var_name});
            try runtime_var_items.append(arena, try aw.toOwnedSlice());
            try runtime_var_symbols.append(arena, .{ .name = emitted_var_name, .symbol = runtime_var_decl.name });
        }
    }
    const runtime_var_texts = try runtime_var_items.toOwnedSlice(arena);
    const runtime_var_symbol_items = try runtime_var_symbols.toOwnedSlice(arena);

    const register_functions_name = if (emits_functions)
        try ctype_resolver.renderFuncName(arena, config, try std.fmt.allocPrint(arena, "{s}_register_functions", .{config.lib_id}))
    else
        "";
    const load_runtime_vars_name = if (has_emitted_runtime_vars)
        try ctype_resolver.renderFuncName(arena, config, try std.fmt.allocPrint(arena, "{s}_load_runtime_vars", .{config.lib_id}))
    else
        "";

    var sections: std.ArrayList(template_sections.TemplateSectionView) = .empty;
    var has_emitted_section = false;
    try template_sections.appendBlockSection(arena, &sections, &has_emitted_section, "type_block", type_block_items, false, true);
    try template_sections.appendBlockSection(arena, &sections, &has_emitted_section, "type_block", public_type_alias_texts, false, false);
    try template_sections.appendBlockSection(arena, &sections, &has_emitted_section, "type_block", auto_callback_type_texts, false, false);
    try template_sections.appendAutoCallbackConstructorsSection(arena, &sections, &has_emitted_section, auto_callback_constructor_view_items);
    if (emits_constants and !has_helper_functions) {
        try template_sections.appendConstBlockSection(arena, &sections, &has_emitted_section, constant_view_items, true);
    }
    try template_sections.appendTextSection(arena, &sections, &has_emitted_section, helper_texts, false);
    if (need_union_helpers) {
        try template_sections.appendUnionHelpersSection(arena, &sections, &has_emitted_section);
    }
    try template_sections.appendStructAccessorsSection(arena, &sections, &has_emitted_section, struct_accessor_view_items);
    if (emits_constants and has_helper_functions) {
        try template_sections.appendConstBlockSection(arena, &sections, &has_emitted_section, constant_view_items, true);
    }
    try template_sections.appendPublicWrappersSection(arena, &sections, &has_emitted_section, public_wrapper_view_items);
    try template_sections.appendBlockSection(arena, &sections, &has_emitted_section, "var_block", function_var_texts, emits_functions, true);
    try template_sections.appendTextSection(arena, &sections, &has_emitted_section, buffer_helper_texts, false);
    try template_sections.appendAutoCallbackWrappersSection(arena, &sections, &has_emitted_section, auto_callback_wrapper_view_items);
    try template_sections.appendOwnedStringHelpersSection(arena, &sections, &has_emitted_section, owned_string_helper_view_items, gostring_name_str);
    try template_sections.appendRegisterFunctionsSection(arena, &sections, &has_emitted_section, true, register_functions_name, register_function_items);
    try template_sections.appendBlockSection(arena, &sections, &has_emitted_section, "var_block", runtime_var_texts, has_emitted_runtime_vars, true);
    try template_sections.appendRuntimeVarLoaderSection(arena, &sections, &has_emitted_section, true, load_runtime_vars_name, runtime_var_symbol_items);
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
    var next_function_index: usize = 0;
    for (decls.functions.items) |func| {
        if (ctype_resolver.isExactExcluded(config.exclude.func_name, func.name)) {
            freeFunctionDecl(allocator, func);
            continue;
        }
        decls.functions.items[next_function_index] = func;
        next_function_index += 1;
    }
    decls.functions.items.len = next_function_index;

    var next_typedef_index: usize = 0;
    for (decls.typedefs.items) |typedef_decl| {
        if (ctype_resolver.isExactExcluded(config.exclude.type_name, typedef_decl.name)) {
            freeTypedefDecl(allocator, typedef_decl);
            continue;
        }
        decls.typedefs.items[next_typedef_index] = typedef_decl;
        next_typedef_index += 1;
    }
    decls.typedefs.items.len = next_typedef_index;

    var next_constant_index: usize = 0;
    for (decls.constants.items) |constant_decl| {
        if (ctype_resolver.isExactExcluded(config.exclude.const_name, constant_decl.name)) {
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
        if (ctype_resolver.isExactExcluded(config.exclude.var_name, runtime_var_decl.name)) {
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
        if (!ctype_resolver.isIncludedOnly(config.include.func_name, func.name)) {
            freeFunctionDecl(allocator, func);
            continue;
        }
        decls.functions.items[next_function_index] = func;
        next_function_index += 1;
    }
    decls.functions.items.len = next_function_index;

    var next_typedef_index: usize = 0;
    for (decls.typedefs.items) |typedef_decl| {
        if (!ctype_resolver.isIncludedOnly(config.include.type_name, typedef_decl.name)) {
            freeTypedefDecl(allocator, typedef_decl);
            continue;
        }
        decls.typedefs.items[next_typedef_index] = typedef_decl;
        next_typedef_index += 1;
    }
    decls.typedefs.items.len = next_typedef_index;

    var next_constant_index: usize = 0;
    for (decls.constants.items) |constant_decl| {
        if (!ctype_resolver.isIncludedOnly(config.include.const_name, constant_decl.name)) {
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
        if (!ctype_resolver.isIncludedOnly(config.include.var_name, runtime_var_decl.name)) {
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
