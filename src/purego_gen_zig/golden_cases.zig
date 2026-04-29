const std = @import("std");
const go_generation = @import("go_generation.zig");

const supported_golden_case_ids = [_][]const u8{
    "abi_types",
    "basic_and_categories",
    "basic_func_type",
    "basic_type_strict_opaque",
    "buffer_input_helper",
    "buffer_input_pattern",
    "by_value_records",
    "callback_auto_discover",
    "callback_param",
    "callback_param_conflict",
    "categories_const",
    "categories_mixed_filtered",
    "comments_default",
    "comments_parse_all",
    "custom_prefix",
    "exclude_only_basic",
    "inline_func_pointer",
    "macro_constants",
    "macro_sentinels",
    "non_callback_typedef",
    "opaque_func_only",
    "owned_string_return",
    "parameter_names",
    "public_api_basic",
    "struct_accessors_basic",
    "void_callback",
};

// Cases intentionally skipped until the Zig generator supports more of the
// Python golden-case surface area.
const unsupported_golden_case_ids = [_][]const u8{
    "callback_param_dedup",
    "conditional_default",
    "conditional_with_define",
    "libclang",
    "libsqlite3",
    "libzstd",
    "prefix_free",
    "runtime_smoke",
    "runtime_string",
    "strict_typing_default",
    "strict_typing_enabled",
    "union_basic",
    "union_basic_accessors",
};

pub const LoadedCase = struct {
    case_dir: []const u8,
    header_paths: [][]const u8,
    expected_path: []const u8,
    clang_args: [][]const u8,
    generator: go_generation.GeneratorConfig,

    pub fn deinit(self: *LoadedCase, allocator: std.mem.Allocator) void {
        allocator.free(self.case_dir);
        for (self.header_paths) |header_path| allocator.free(header_path);
        allocator.free(self.header_paths);
        allocator.free(self.expected_path);
        for (self.clang_args) |arg| allocator.free(arg);
        allocator.free(self.clang_args);
        self.generator.deinit(allocator);
    }
};

fn parseEmitKinds(
    allocator: std.mem.Allocator,
    array: std.json.Array,
) ![]go_generation.EmitKind {
    var items: std.ArrayList(go_generation.EmitKind) = .empty;
    errdefer items.deinit(allocator);
    for (array.items) |item| {
        const raw = item.string;
        if (std.mem.eql(u8, raw, "func")) {
            try items.append(allocator, .func);
        } else if (std.mem.eql(u8, raw, "type")) {
            try items.append(allocator, .type);
        } else if (std.mem.eql(u8, raw, "const")) {
            try items.append(allocator, .@"const");
        } else if (std.mem.eql(u8, raw, "var")) {
            try items.append(allocator, .var_decl);
        } else {
            return error.UnsupportedEmitKind;
        }
    }
    return items.toOwnedSlice(allocator);
}

fn parseStringArray(allocator: std.mem.Allocator, array: std.json.Array) ![][]const u8 {
    var items: std.ArrayList([]const u8) = .empty;
    errdefer {
        for (items.items) |item| allocator.free(item);
        items.deinit(allocator);
    }
    for (array.items) |item| {
        try items.append(allocator, try allocator.dupe(u8, item.string));
    }
    return items.toOwnedSlice(allocator);
}

fn freeBufferParamHelpers(
    allocator: std.mem.Allocator,
    helpers: []const go_generation.BufferParamHelper,
) void {
    for (helpers) |helper| {
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
    allocator.free(helpers);
}

fn freeCallbackParamHelpers(
    allocator: std.mem.Allocator,
    helpers: []const go_generation.ExplicitCallbackParamHelper,
) void {
    for (helpers) |helper| {
        allocator.free(helper.function_name);
        for (helper.params) |param| allocator.free(param);
        allocator.free(helper.params);
    }
    allocator.free(helpers);
}

fn freeOwnedStringReturnHelpers(
    allocator: std.mem.Allocator,
    helpers: []const go_generation.OwnedStringReturnHelper,
) void {
    for (helpers) |helper| {
        allocator.free(helper.function_name);
        allocator.free(helper.free_func_name);
    }
    allocator.free(helpers);
}

fn freePublicApiMatchers(
    allocator: std.mem.Allocator,
    matchers: []const go_generation.PublicApiMatcher,
) void {
    for (matchers) |matcher| {
        switch (matcher) {
            .exact => |value| allocator.free(value),
            .pattern => |value| allocator.free(value),
        }
    }
    allocator.free(matchers);
}

fn freePublicApiOverrides(
    allocator: std.mem.Allocator,
    overrides: []const go_generation.PublicApiOverride,
) void {
    for (overrides) |override| {
        allocator.free(override.source_name);
        allocator.free(override.public_name);
    }
    allocator.free(overrides);
}

fn parseNamingValue(
    allocator: std.mem.Allocator,
    render: std.json.ObjectMap,
    key: []const u8,
) ![]const u8 {
    const naming_value = render.get("naming") orelse return allocator.dupe(u8, "");
    const naming = naming_value.object;
    const value = naming.get(key) orelse return allocator.dupe(u8, "");
    return allocator.dupe(u8, value.string);
}

fn parseExcludeValue(
    allocator: std.mem.Allocator,
    parse: std.json.ObjectMap,
    key: []const u8,
) ![]const u8 {
    const exclude_value = parse.get("exclude") orelse return allocator.dupe(u8, "");
    const exclude = exclude_value.object;
    const value = exclude.get(key) orelse return allocator.dupe(u8, "");
    return allocator.dupe(u8, value.string);
}

fn parseIncludeValue(
    allocator: std.mem.Allocator,
    parse: std.json.ObjectMap,
    key: []const u8,
) ![]const u8 {
    const include_value = parse.get("include") orelse return allocator.dupe(u8, "");
    const include = include_value.object;
    const value = include.get(key) orelse return allocator.dupe(u8, "");
    return switch (value) {
        .string => |string| allocator.dupe(u8, string),
        else => allocator.dupe(u8, ""),
    };
}

fn parseBufferParamPairs(
    allocator: std.mem.Allocator,
    array: std.json.Array,
) ![]go_generation.BufferParamPair {
    var items: std.ArrayList(go_generation.BufferParamPair) = .empty;
    errdefer {
        for (items.items) |pair| {
            allocator.free(pair.pointer);
            allocator.free(pair.length);
        }
        items.deinit(allocator);
    }

    for (array.items) |item| {
        const obj = item.object;
        try items.append(allocator, .{
            .pointer = try allocator.dupe(u8, obj.get("pointer").?.string),
            .length = try allocator.dupe(u8, obj.get("length").?.string),
        });
    }

    return items.toOwnedSlice(allocator);
}

fn parsePublicApiMatchers(
    allocator: std.mem.Allocator,
    value: ?std.json.Value,
) ![]go_generation.PublicApiMatcher {
    const matchers_value = value orelse return try allocator.alloc(go_generation.PublicApiMatcher, 0);
    var items: std.ArrayList(go_generation.PublicApiMatcher) = .empty;
    errdefer {
        for (items.items) |matcher| {
            switch (matcher) {
                .exact => |string| allocator.free(string),
                .pattern => |string| allocator.free(string),
            }
        }
        items.deinit(allocator);
    }

    for (matchers_value.array.items) |item| {
        switch (item) {
            .string => |string| try items.append(allocator, .{
                .exact = try allocator.dupe(u8, string),
            }),
            .object => |obj| {
                const pattern_value = obj.get("pattern") orelse return error.MissingPublicApiPattern;
                try items.append(allocator, .{
                    .pattern = try allocator.dupe(u8, pattern_value.string),
                });
            },
            else => return error.InvalidPublicApiMatcher,
        }
    }

    return items.toOwnedSlice(allocator);
}

fn parsePublicApiOverrides(
    allocator: std.mem.Allocator,
    value: ?std.json.Value,
) ![]go_generation.PublicApiOverride {
    const overrides_value = value orelse return try allocator.alloc(go_generation.PublicApiOverride, 0);
    var items: std.ArrayList(go_generation.PublicApiOverride) = .empty;
    errdefer {
        for (items.items) |override| {
            allocator.free(override.source_name);
            allocator.free(override.public_name);
        }
        items.deinit(allocator);
    }

    var iterator = overrides_value.object.iterator();
    while (iterator.next()) |entry| {
        try items.append(allocator, .{
            .source_name = try allocator.dupe(u8, entry.key_ptr.*),
            .public_name = try allocator.dupe(u8, entry.value_ptr.*.string),
        });
    }

    return items.toOwnedSlice(allocator);
}

fn parsePublicApiConfig(
    allocator: std.mem.Allocator,
    generator: std.json.ObjectMap,
) !go_generation.PublicApiConfig {
    const render_value = generator.get("render") orelse return .{
        .strip_prefix = try allocator.dupe(u8, ""),
        .type_aliases_include = try allocator.alloc(go_generation.PublicApiMatcher, 0),
        .type_aliases_overrides = try allocator.alloc(go_generation.PublicApiOverride, 0),
        .wrappers_include = try allocator.alloc(go_generation.PublicApiMatcher, 0),
        .wrappers_exclude = try allocator.alloc(go_generation.PublicApiMatcher, 0),
        .wrappers_overrides = try allocator.alloc(go_generation.PublicApiOverride, 0),
    };
    const render = render_value.object;
    const public_api_value = render.get("public_api") orelse return .{
        .strip_prefix = try allocator.dupe(u8, ""),
        .type_aliases_include = try allocator.alloc(go_generation.PublicApiMatcher, 0),
        .type_aliases_overrides = try allocator.alloc(go_generation.PublicApiOverride, 0),
        .wrappers_include = try allocator.alloc(go_generation.PublicApiMatcher, 0),
        .wrappers_exclude = try allocator.alloc(go_generation.PublicApiMatcher, 0),
        .wrappers_overrides = try allocator.alloc(go_generation.PublicApiOverride, 0),
    };
    const public_api = public_api_value.object;
    const type_aliases = public_api.get("type_aliases");
    const wrappers = public_api.get("wrappers");

    return .{
        .strip_prefix = if (public_api.get("strip_prefix")) |value|
            try allocator.dupe(u8, value.string)
        else
            try allocator.dupe(u8, ""),
        .type_aliases_include = try parsePublicApiMatchers(allocator, if (type_aliases) |value| value.object.get("include") else null),
        .type_aliases_overrides = try parsePublicApiOverrides(allocator, if (type_aliases) |value| value.object.get("overrides") else null),
        .wrappers_include = try parsePublicApiMatchers(allocator, if (wrappers) |value| value.object.get("include") else null),
        .wrappers_exclude = try parsePublicApiMatchers(allocator, if (wrappers) |value| value.object.get("exclude") else null),
        .wrappers_overrides = try parsePublicApiOverrides(allocator, if (wrappers) |value| value.object.get("overrides") else null),
    };
}

fn parseCallbackParamHelpers(
    allocator: std.mem.Allocator,
    generator: std.json.ObjectMap,
) ![]go_generation.ExplicitCallbackParamHelper {
    const render_value = generator.get("render") orelse return try allocator.alloc(go_generation.ExplicitCallbackParamHelper, 0);
    const render = render_value.object;
    const helpers_value = render.get("helpers") orelse return try allocator.alloc(go_generation.ExplicitCallbackParamHelper, 0);
    const helpers = helpers_value.object;
    const callback_params_value = helpers.get("callback_params") orelse return try allocator.alloc(go_generation.ExplicitCallbackParamHelper, 0);

    var items: std.ArrayList(go_generation.ExplicitCallbackParamHelper) = .empty;
    errdefer {
        for (items.items) |helper| {
            allocator.free(helper.function_name);
            for (helper.params) |param| allocator.free(param);
            allocator.free(helper.params);
        }
        items.deinit(allocator);
    }

    for (callback_params_value.array.items) |item| {
        const obj = item.object;
        const function_value = obj.get("function") orelse return error.MissingCallbackHelperFunction;
        const params_value = obj.get("params") orelse return error.MissingCallbackHelperParams;
        try items.append(allocator, .{
            .function_name = try allocator.dupe(u8, function_value.string),
            .params = try parseStringArray(allocator, params_value.array),
        });
    }

    return items.toOwnedSlice(allocator);
}

fn parseOwnedStringReturnHelpers(
    allocator: std.mem.Allocator,
    generator: std.json.ObjectMap,
) ![]go_generation.OwnedStringReturnHelper {
    const render_value = generator.get("render") orelse return try allocator.alloc(go_generation.OwnedStringReturnHelper, 0);
    const render = render_value.object;
    const helpers_value = render.get("helpers") orelse return try allocator.alloc(go_generation.OwnedStringReturnHelper, 0);
    const helpers = helpers_value.object;
    const owned_value = helpers.get("owned_string_returns") orelse return try allocator.alloc(go_generation.OwnedStringReturnHelper, 0);

    var items: std.ArrayList(go_generation.OwnedStringReturnHelper) = .empty;
    errdefer {
        for (items.items) |helper| {
            allocator.free(helper.function_name);
            allocator.free(helper.free_func_name);
        }
        items.deinit(allocator);
    }

    for (owned_value.array.items) |item| {
        const obj = item.object;
        const function_value = obj.get("function") orelse return error.MissingOwnedStringHelperFunction;
        const free_func_value = obj.get("free_func") orelse return error.MissingOwnedStringHelperFreeFunction;
        switch (function_value) {
            .string => try items.append(allocator, .{
                .function_name = try allocator.dupe(u8, function_value.string),
                .free_func_name = try allocator.dupe(u8, free_func_value.string),
            }),
            else => return error.InvalidOwnedStringHelperFunction,
        }
    }

    return items.toOwnedSlice(allocator);
}

fn parseBufferParamHelpers(
    allocator: std.mem.Allocator,
    generator: std.json.ObjectMap,
) ![]go_generation.BufferParamHelper {
    const render_value = generator.get("render") orelse return try allocator.alloc(go_generation.BufferParamHelper, 0);
    const render = render_value.object;
    const helpers_value = render.get("helpers") orelse return try allocator.alloc(go_generation.BufferParamHelper, 0);
    const helpers = helpers_value.object;
    const buffer_params_value = helpers.get("buffer_params") orelse return try allocator.alloc(go_generation.BufferParamHelper, 0);

    var items: std.ArrayList(go_generation.BufferParamHelper) = .empty;
    errdefer {
        for (items.items) |helper| {
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
        items.deinit(allocator);
    }

    for (buffer_params_value.array.items) |item| {
        const obj = item.object;
        const function_value = obj.get("function") orelse return error.MissingBufferHelperFunction;
        switch (function_value) {
            .string => {
                const pairs_value = obj.get("pairs") orelse return error.MissingBufferHelperPairs;
                try items.append(allocator, .{
                    .explicit = .{
                        .function_name = try allocator.dupe(u8, function_value.string),
                        .pairs = try parseBufferParamPairs(allocator, pairs_value.array),
                    },
                });
            },
            .object => {
                const pattern_value = function_value.object.get("pattern") orelse return error.MissingBufferHelperPattern;
                try items.append(allocator, .{
                    .pattern = .{
                        .function_pattern = try allocator.dupe(u8, pattern_value.string),
                    },
                });
            },
            else => return error.InvalidBufferHelperFunction,
        }
    }

    return items.toOwnedSlice(allocator);
}

fn joinCasePath(
    allocator: std.mem.Allocator,
    case_dir: []const u8,
    relative_path: []const u8,
) ![]const u8 {
    return std.fs.path.join(allocator, &.{ case_dir, relative_path });
}

pub fn loadCaseFromDir(
    allocator: std.mem.Allocator,
    case_dir: []const u8,
) !LoadedCase {
    const config_path = try std.fs.path.join(allocator, &.{ case_dir, "config.json" });
    defer allocator.free(config_path);

    const io = std.Io.Threaded.global_single_threaded.io();
    const config_raw = try std.Io.Dir.cwd().readFileAlloc(io, config_path, allocator, .limited(1024 * 1024));
    defer allocator.free(config_raw);

    var parsed = try std.json.parseFromSlice(std.json.Value, allocator, config_raw, .{});
    defer parsed.deinit();

    const root = parsed.value.object;
    const generator_obj = root.get("generator") orelse return error.MissingGeneratorConfig;
    const generator = generator_obj.object;

    const parse_obj = generator.get("parse") orelse return error.MissingParseConfig;
    const parse = parse_obj.object;
    const headers_obj = parse.get("headers") orelse return error.MissingHeadersConfig;
    const headers = headers_obj.object;
    const headers_kind = headers.get("kind") orelse return error.MissingHeadersKind;
    const is_local = std.mem.eql(u8, headers_kind.string, "local");
    const is_env_include = std.mem.eql(u8, headers_kind.string, "env_include");
    if (!is_local and !is_env_include) {
        return error.UnsupportedHeadersKind;
    }

    var include_dir_owned: ?[]u8 = null;
    defer if (include_dir_owned) |dir| allocator.free(dir);
    if (is_env_include) {
        const include_dir_env_value = headers.get("include_dir_env") orelse return error.MissingIncludeDirEnv;
        const env_name = try allocator.dupeZ(u8, include_dir_env_value.string);
        defer allocator.free(env_name);
        const raw = std.c.getenv(env_name.ptr) orelse return error.RequiredIncludeDirEnvNotSet;
        const trimmed = std.mem.trim(u8, std.mem.span(raw), &std.ascii.whitespace);
        if (trimmed.len == 0) return error.RequiredIncludeDirEnvNotSet;
        std.Io.Dir.cwd().access(io, trimmed, .{}) catch return error.IncludeDirNotFound;
        include_dir_owned = try allocator.dupe(u8, trimmed);
    }
    const header_base_dir: []const u8 = if (include_dir_owned) |dir| dir else case_dir;

    const header_list_value = headers.get("headers") orelse return error.MissingHeadersList;
    const emit_value = generator.get("emit") orelse return error.MissingEmitConfig;
    const emit = try parseEmitKinds(allocator, emit_value.array);
    errdefer allocator.free(emit);
    const buffer_param_helpers = try parseBufferParamHelpers(allocator, generator);
    errdefer freeBufferParamHelpers(allocator, buffer_param_helpers);
    const callback_param_helpers = try parseCallbackParamHelpers(allocator, generator);
    errdefer freeCallbackParamHelpers(allocator, callback_param_helpers);
    const owned_string_return_helpers = try parseOwnedStringReturnHelpers(allocator, generator);
    errdefer freeOwnedStringReturnHelpers(allocator, owned_string_return_helpers);
    const public_api = try parsePublicApiConfig(allocator, generator);
    errdefer {
        allocator.free(public_api.strip_prefix);
        freePublicApiMatchers(allocator, public_api.type_aliases_include);
        freePublicApiOverrides(allocator, public_api.type_aliases_overrides);
        freePublicApiMatchers(allocator, public_api.wrappers_include);
        freePublicApiMatchers(allocator, public_api.wrappers_exclude);
        freePublicApiOverrides(allocator, public_api.wrappers_overrides);
    }

    const header_paths = try parseStringArray(allocator, header_list_value.array);
    errdefer {
        for (header_paths) |header_path| allocator.free(header_path);
        allocator.free(header_paths);
    }

    const clang_args = blk: {
        const config_clang_args = if (parse.get("clang_args")) |clang_args_value|
            try parseStringArray(allocator, clang_args_value.array)
        else
            try allocator.alloc([]const u8, 0);
        errdefer {
            for (config_clang_args) |arg| allocator.free(arg);
            allocator.free(config_clang_args);
        }

        const dir = include_dir_owned orelse break :blk config_clang_args;
        const combined = try allocator.alloc([]const u8, config_clang_args.len + 2);
        errdefer allocator.free(combined);
        combined[0] = try allocator.dupe(u8, "-I");
        errdefer allocator.free(combined[0]);
        combined[1] = try allocator.dupe(u8, dir);
        @memcpy(combined[2..], config_clang_args);
        allocator.free(config_clang_args);
        break :blk combined;
    };
    errdefer {
        for (clang_args) |arg| allocator.free(arg);
        allocator.free(clang_args);
    }

    const resolved_header_paths = blk: {
        var resolved_paths: std.ArrayList([]const u8) = .empty;
        errdefer {
            for (resolved_paths.items) |resolved_path| allocator.free(resolved_path);
            resolved_paths.deinit(allocator);
        }
        for (header_paths) |header_path| {
            try resolved_paths.append(allocator, try joinCasePath(allocator, header_base_dir, header_path));
        }
        break :blk try resolved_paths.toOwnedSlice(allocator);
    };
    for (header_paths) |header_path| allocator.free(header_path);
    allocator.free(header_paths);

    return .{
        .case_dir = try allocator.dupe(u8, case_dir),
        .header_paths = resolved_header_paths,
        .expected_path = try std.fs.path.join(allocator, &.{ case_dir, "generated.go" }),
        .clang_args = clang_args,
        .generator = .{
            .lib_id = try allocator.dupe(u8, generator.get("lib_id").?.string),
            .package_name = try allocator.dupe(u8, generator.get("package").?.string),
            .emit = emit,
            .naming = blk: {
                const render_value = generator.get("render") orelse break :blk .{
                    .type_prefix = try allocator.dupe(u8, ""),
                    .const_prefix = try allocator.dupe(u8, ""),
                    .func_prefix = try allocator.dupe(u8, ""),
                    .var_prefix = try allocator.dupe(u8, ""),
                };
                const render = render_value.object;
                break :blk .{
                    .type_prefix = try parseNamingValue(allocator, render, "type_prefix"),
                    .const_prefix = try parseNamingValue(allocator, render, "const_prefix"),
                    .func_prefix = try parseNamingValue(allocator, render, "func_prefix"),
                    .var_prefix = try parseNamingValue(allocator, render, "var_prefix"),
                };
            },
            .include = .{
                .func_name = try parseIncludeValue(allocator, parse, "func"),
                .type_name = try parseIncludeValue(allocator, parse, "type"),
                .const_name = try parseIncludeValue(allocator, parse, "const"),
                .var_name = try parseIncludeValue(allocator, parse, "var"),
            },
            .exclude = .{
                .func_name = try parseExcludeValue(allocator, parse, "func"),
                .type_name = try parseExcludeValue(allocator, parse, "type"),
                .const_name = try parseExcludeValue(allocator, parse, "const"),
                .var_name = try parseExcludeValue(allocator, parse, "var"),
            },
            .typed_sentinel_constants = blk: {
                const render_value = generator.get("render") orelse break :blk false;
                const render = render_value.object;
                const type_mapping_value = render.get("type_mapping") orelse break :blk false;
                const type_mapping = type_mapping_value.object;
                const typed_sentinel_value = type_mapping.get("typed_sentinel_constants") orelse break :blk false;
                break :blk typed_sentinel_value.bool;
            },
            .strict_enum_typedefs = blk: {
                const render_value = generator.get("render") orelse break :blk false;
                const render = render_value.object;
                const type_mapping_value = render.get("type_mapping") orelse break :blk false;
                const type_mapping = type_mapping_value.object;
                const strict_enum_value = type_mapping.get("strict_enum_typedefs") orelse break :blk false;
                break :blk strict_enum_value.bool;
            },
            .struct_accessors = blk: {
                const render_value = generator.get("render") orelse break :blk false;
                const render = render_value.object;
                const struct_accessors_value = render.get("struct_accessors") orelse break :blk false;
                break :blk struct_accessors_value.bool;
            },
            .buffer_param_helpers = buffer_param_helpers,
            .callback_param_helpers = callback_param_helpers,
            .owned_string_return_helpers = owned_string_return_helpers,
            .public_api = public_api,
            .auto_callbacks = blk: {
                const render_value = generator.get("render") orelse break :blk false;
                const render = render_value.object;
                const auto_callbacks_value = render.get("auto_callbacks") orelse break :blk false;
                break :blk auto_callbacks_value.bool;
            },
        },
    };
}

fn dupeZString(allocator: std.mem.Allocator, value: []const u8) ![:0]u8 {
    return allocator.dupeZ(u8, value);
}

fn dupeZStringArray(
    allocator: std.mem.Allocator,
    items: [][]const u8,
) ![][*:0]const u8 {
    var out = try allocator.alloc([*:0]const u8, items.len);
    errdefer allocator.free(out);

    for (items, 0..) |item, i| {
        const duped = try allocator.dupeZ(u8, item);
        out[i] = duped.ptr;
    }
    return out;
}

fn freeZStringArray(
    allocator: std.mem.Allocator,
    items: [][*:0]const u8,
) void {
    for (items) |item| {
        const sentinel_slice: [:0]const u8 = std.mem.span(item);
        allocator.free(sentinel_slice);
    }
    allocator.free(items);
}

pub fn generateCaseSource(
    allocator: std.mem.Allocator,
    loaded_case: *const LoadedCase,
    skip_gofmt: bool,
) ![]u8 {
    const header_paths_z = try allocator.alloc([:0]const u8, loaded_case.header_paths.len);
    defer {
        for (header_paths_z) |header_path_z| allocator.free(header_path_z);
        allocator.free(header_paths_z);
    }
    for (loaded_case.header_paths, 0..) |header_path, i| {
        header_paths_z[i] = try dupeZString(allocator, header_path);
    }

    const clang_args_z = try dupeZStringArray(allocator, loaded_case.clang_args);
    defer freeZStringArray(allocator, clang_args_z);

    var decls = try go_generation.collectDeclarationsFromHeaders(
        allocator,
        header_paths_z,
        clang_args_z,
    );
    defer decls.deinit();
    go_generation.applyIncludeFilters(allocator, loaded_case.generator, &decls);
    go_generation.applyExcludeFilters(allocator, loaded_case.generator, &decls);

    return go_generation.generateGoSource(allocator, loaded_case.generator, &decls, skip_gofmt);
}

pub fn expectCaseMatchesGeneratedGo(
    allocator: std.mem.Allocator,
    case_dir: []const u8,
) !void {
    var loaded_case = try loadCaseFromDir(allocator, case_dir);
    defer loaded_case.deinit(allocator);

    const io = std.Io.Threaded.global_single_threaded.io();
    const expected = try std.Io.Dir.cwd().readFileAlloc(io, loaded_case.expected_path, allocator, .limited(1024 * 1024));
    defer allocator.free(expected);

    const skip_gofmt = if (std.c.getenv("PUREGO_GEN_SKIP_GOFMT")) |val| blk: {
        const slice = std.mem.span(val);
        break :blk std.mem.eql(u8, slice, "1") or std.mem.eql(u8, slice, "true");
    } else false;
    const actual = try generateCaseSource(allocator, &loaded_case, skip_gofmt);
    defer allocator.free(actual);

    try std.testing.expectEqualStrings(expected, actual);
}

fn expectCaseIdMatchesGeneratedGo(
    allocator: std.mem.Allocator,
    case_id: []const u8,
) !void {
    const case_dir = try std.fs.path.join(allocator, &.{ "tests/cases", case_id });
    defer allocator.free(case_dir);
    try expectCaseMatchesGeneratedGo(allocator, case_dir);
}

test "allowlisted golden cases match generated.go" {
    inline for (supported_golden_case_ids) |case_id| {
        try expectCaseIdMatchesGeneratedGo(std.testing.allocator, case_id);
    }
}

test "golden case allowlist is partitioned" {
    for (supported_golden_case_ids) |supported_case_id| {
        for (unsupported_golden_case_ids) |unsupported_case_id| {
            try std.testing.expect(!std.mem.eql(u8, supported_case_id, unsupported_case_id));
        }
    }
}
