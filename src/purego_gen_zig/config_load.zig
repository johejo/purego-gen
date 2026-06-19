const std = @import("std");
const go_generation = @import("go_generation.zig");

/// One fully-resolved generator configuration: header paths and clang args are
/// resolved to concrete strings, ready to feed into declaration collection and
/// Go source generation. This is the shared form consumed by both the golden
/// case harness and the user-facing `gen` CLI.
pub const LoadedConfig = struct {
    header_paths: [][]const u8,
    clang_args: [][]const u8,
    generator: go_generation.GeneratorConfig,

    pub fn deinit(self: *LoadedConfig, allocator: std.mem.Allocator) void {
        for (self.header_paths) |header_path| allocator.free(header_path);
        allocator.free(self.header_paths);
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

fn freeOwnedSlice(comptime T: type, allocator: std.mem.Allocator, items: []const T) void {
    for (items) |item| item.deinit(allocator);
    allocator.free(items);
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

fn parseStringOrStringArray(
    allocator: std.mem.Allocator,
    value: std.json.Value,
) ![][]const u8 {
    return switch (value) {
        .string => |string| blk: {
            var items = try allocator.alloc([]const u8, 1);
            errdefer allocator.free(items);
            items[0] = try allocator.dupe(u8, string);
            break :blk items;
        },
        .array => |array| try parseStringArray(allocator, array),
        else => error.InvalidIncludeOrExcludeValue,
    };
}

fn parseExcludeValue(
    allocator: std.mem.Allocator,
    parse: std.json.ObjectMap,
    key: []const u8,
) ![][]const u8 {
    const exclude_value = parse.get("exclude") orelse return try allocator.alloc([]const u8, 0);
    const exclude = exclude_value.object;
    const value = exclude.get(key) orelse return try allocator.alloc([]const u8, 0);
    return parseStringOrStringArray(allocator, value);
}

fn parseIncludeValue(
    allocator: std.mem.Allocator,
    parse: std.json.ObjectMap,
    key: []const u8,
) ![][]const u8 {
    const include_value = parse.get("include") orelse return try allocator.alloc([]const u8, 0);
    const include = include_value.object;
    const value = include.get(key) orelse return try allocator.alloc([]const u8, 0);
    return parseStringOrStringArray(allocator, value);
}

fn parseBufferParamPairs(
    allocator: std.mem.Allocator,
    array: std.json.Array,
) ![]go_generation.BufferParamPair {
    var items: std.ArrayList(go_generation.BufferParamPair) = .empty;
    errdefer {
        for (items.items) |pair| pair.deinit(allocator);
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
        for (items.items) |matcher| matcher.deinit(allocator);
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
        for (items.items) |override| override.deinit(allocator);
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
        for (items.items) |helper| helper.deinit(allocator);
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
        for (items.items) |helper| helper.deinit(allocator);
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
        for (items.items) |helper| helper.deinit(allocator);
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

fn joinPath(
    allocator: std.mem.Allocator,
    base_dir: []const u8,
    relative_path: []const u8,
) ![]const u8 {
    return std.fs.path.join(allocator, &.{ base_dir, relative_path });
}

/// Parse an application config (`schema_version` + `generator` block) from raw
/// JSON bytes into a `LoadedConfig`. `base_dir` is the directory used to resolve
/// `kind: "local"` header paths (typically the directory containing the config
/// file). `env_include` headers resolve their include directory from the named
/// environment variable and prepend `-I <dir>` to the clang args.
pub fn loadFromText(
    allocator: std.mem.Allocator,
    json_bytes: []const u8,
    base_dir: []const u8,
) !LoadedConfig {
    const io = std.Io.Threaded.global_single_threaded.io();

    var parsed = try std.json.parseFromSlice(std.json.Value, allocator, json_bytes, .{});
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
    const header_base_dir: []const u8 = if (include_dir_owned) |dir| dir else base_dir;

    const header_list_value = headers.get("headers") orelse return error.MissingHeadersList;
    const emit_value = generator.get("emit") orelse return error.MissingEmitConfig;
    const emit = try parseEmitKinds(allocator, emit_value.array);
    errdefer allocator.free(emit);
    const buffer_param_helpers = try parseBufferParamHelpers(allocator, generator);
    errdefer freeOwnedSlice(go_generation.BufferParamHelper, allocator, buffer_param_helpers);
    const callback_param_helpers = try parseCallbackParamHelpers(allocator, generator);
    errdefer freeOwnedSlice(go_generation.ExplicitCallbackParamHelper, allocator, callback_param_helpers);
    const owned_string_return_helpers = try parseOwnedStringReturnHelpers(allocator, generator);
    errdefer freeOwnedSlice(go_generation.OwnedStringReturnHelper, allocator, owned_string_return_helpers);
    const public_api = try parsePublicApiConfig(allocator, generator);
    errdefer public_api.deinit(allocator);

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
            try resolved_paths.append(allocator, try joinPath(allocator, header_base_dir, header_path));
        }
        break :blk try resolved_paths.toOwnedSlice(allocator);
    };
    for (header_paths) |header_path| allocator.free(header_path);
    allocator.free(header_paths);

    return .{
        .header_paths = resolved_header_paths,
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
                .func_names = try parseIncludeValue(allocator, parse, "func"),
                .type_names = try parseIncludeValue(allocator, parse, "type"),
                .const_names = try parseIncludeValue(allocator, parse, "const"),
                .var_names = try parseIncludeValue(allocator, parse, "var"),
            },
            .exclude = .{
                .func_names = try parseExcludeValue(allocator, parse, "func"),
                .type_names = try parseExcludeValue(allocator, parse, "type"),
                .const_names = try parseExcludeValue(allocator, parse, "const"),
                .var_names = try parseExcludeValue(allocator, parse, "var"),
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

/// Read and parse an application config from a file path. `kind: "local"` header
/// paths are resolved relative to the config file's directory.
pub fn loadFromPath(
    allocator: std.mem.Allocator,
    config_path: []const u8,
) !LoadedConfig {
    const io = std.Io.Threaded.global_single_threaded.io();
    const config_raw = try std.Io.Dir.cwd().readFileAlloc(io, config_path, allocator, .limited(1024 * 1024));
    defer allocator.free(config_raw);

    const base_dir = std.fs.path.dirname(config_path) orelse ".";
    return loadFromText(allocator, config_raw, base_dir);
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

/// Collect declarations from a resolved config's headers, apply include/exclude
/// filters, and render the formatted Go source.
pub fn generateSource(
    allocator: std.mem.Allocator,
    cfg: *const LoadedConfig,
    skip_gofmt: bool,
) ![]u8 {
    const header_paths_z = try allocator.alloc([:0]const u8, cfg.header_paths.len);
    defer {
        for (header_paths_z) |header_path_z| allocator.free(header_path_z);
        allocator.free(header_paths_z);
    }
    for (cfg.header_paths, 0..) |header_path, i| {
        header_paths_z[i] = try dupeZString(allocator, header_path);
    }

    const clang_args_z = try dupeZStringArray(allocator, cfg.clang_args);
    defer freeZStringArray(allocator, clang_args_z);

    var decls = try go_generation.collectDeclarationsFromHeaders(
        allocator,
        header_paths_z,
        clang_args_z,
    );
    defer decls.deinit();
    go_generation.applyIncludeFilters(allocator, cfg.generator, &decls);
    go_generation.applyExcludeFilters(allocator, cfg.generator, &decls);

    return go_generation.generateGoSource(allocator, cfg.generator, &decls, skip_gofmt);
}

test "loadFromText parses config and resolves header paths against base_dir" {
    const allocator = std.testing.allocator;
    const json =
        \\{
        \\  "schema_version": 2,
        \\  "generator": {
        \\    "lib_id": "demo",
        \\    "package": "demopkg",
        \\    "emit": ["func", "type"],
        \\    "parse": {
        \\      "headers": { "kind": "local", "headers": ["a.h", "b.h"] },
        \\      "clang_args": ["-DFOO=1"],
        \\      "include": { "func": ["foo", "bar"] },
        \\      "exclude": { "type": "Baz" }
        \\    },
        \\    "render": {
        \\      "struct_accessors": true,
        \\      "naming": { "func_prefix": "demo_" }
        \\    }
        \\  }
        \\}
    ;

    var loaded = try loadFromText(allocator, json, "base/dir");
    defer loaded.deinit(allocator);

    try std.testing.expectEqualStrings("demo", loaded.generator.lib_id);
    try std.testing.expectEqualStrings("demopkg", loaded.generator.package_name);

    try std.testing.expectEqual(@as(usize, 2), loaded.generator.emit.len);
    try std.testing.expectEqual(@as(go_generation.EmitKind, .func), loaded.generator.emit[0]);
    try std.testing.expectEqual(@as(go_generation.EmitKind, .type), loaded.generator.emit[1]);

    // Header paths are resolved relative to base_dir; this is the behavior the
    // stdin/in-memory entry relies on (golden cases only exercise loadFromPath).
    try std.testing.expectEqual(@as(usize, 2), loaded.header_paths.len);
    const expected_a = try std.fs.path.join(allocator, &.{ "base/dir", "a.h" });
    defer allocator.free(expected_a);
    const expected_b = try std.fs.path.join(allocator, &.{ "base/dir", "b.h" });
    defer allocator.free(expected_b);
    try std.testing.expectEqualStrings(expected_a, loaded.header_paths[0]);
    try std.testing.expectEqualStrings(expected_b, loaded.header_paths[1]);

    // Local headers do not prepend an include dir, so clang_args pass through.
    try std.testing.expectEqual(@as(usize, 1), loaded.clang_args.len);
    try std.testing.expectEqualStrings("-DFOO=1", loaded.clang_args[0]);

    try std.testing.expectEqual(@as(usize, 2), loaded.generator.include.func_names.len);
    try std.testing.expectEqualStrings("foo", loaded.generator.include.func_names[0]);
    try std.testing.expectEqualStrings("bar", loaded.generator.include.func_names[1]);
    try std.testing.expectEqual(@as(usize, 1), loaded.generator.exclude.type_names.len);
    try std.testing.expectEqualStrings("Baz", loaded.generator.exclude.type_names[0]);

    try std.testing.expect(loaded.generator.struct_accessors);
    try std.testing.expectEqualStrings("demo_", loaded.generator.naming.func_prefix);
}
