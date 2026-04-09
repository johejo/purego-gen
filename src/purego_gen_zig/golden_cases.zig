const std = @import("std");
const go_generation = @import("go_generation.zig");

const supported_golden_case_ids = [_][]const u8{
    "basic_func_type",
};

// Cases intentionally skipped until the Zig generator supports more of the
// Python golden-case surface area.
const unsupported_golden_case_ids = [_][]const u8{
    "abi_types",
    "basic_and_categories",
    "basic_type_strict_opaque",
    "buffer_input_helper",
    "buffer_input_pattern",
    "by_value_records",
    "callback_auto_discover",
    "callback_param",
    "callback_param_conflict",
    "callback_param_dedup",
    "categories_const",
    "categories_mixed_filtered",
    "comments_default",
    "comments_parse_all",
    "conditional_default",
    "conditional_with_define",
    "custom_prefix",
    "exclude_only_basic",
    "inline_func_pointer",
    "libclang",
    "libsqlite3",
    "libzstd",
    "macro_constants",
    "macro_sentinels",
    "non_callback_typedef",
    "opaque_func_only",
    "owned_string_return",
    "parameter_names",
    "prefix_free",
    "public_api_basic",
    "runtime_smoke",
    "runtime_string",
    "strict_typing_default",
    "strict_typing_enabled",
    "struct_accessors_basic",
    "union_basic",
    "union_basic_accessors",
    "void_callback",
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
        allocator.free(self.generator.lib_id);
        allocator.free(self.generator.package_name);
        allocator.free(self.generator.emit);
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

    const config_raw = try std.fs.cwd().readFileAlloc(allocator, config_path, 1024 * 1024);
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
    if (!std.mem.eql(u8, headers_kind.string, "local")) {
        return error.UnsupportedHeadersKind;
    }

    const header_list_value = headers.get("headers") orelse return error.MissingHeadersList;
    const emit_value = generator.get("emit") orelse return error.MissingEmitConfig;
    const emit = try parseEmitKinds(allocator, emit_value.array);
    errdefer allocator.free(emit);

    const header_paths = try parseStringArray(allocator, header_list_value.array);
    errdefer {
        for (header_paths) |header_path| allocator.free(header_path);
        allocator.free(header_paths);
    }

    const clang_args = if (parse.get("clang_args")) |clang_args_value|
        try parseStringArray(allocator, clang_args_value.array)
    else
        try allocator.alloc([]const u8, 0);
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
            try resolved_paths.append(allocator, try joinCasePath(allocator, case_dir, header_path));
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

    return go_generation.generateGoSource(allocator, loaded_case.generator, &decls);
}

pub fn expectCaseMatchesGeneratedGo(
    allocator: std.mem.Allocator,
    case_dir: []const u8,
) !void {
    var loaded_case = try loadCaseFromDir(allocator, case_dir);
    defer loaded_case.deinit(allocator);

    const expected = try std.fs.cwd().readFileAlloc(allocator, loaded_case.expected_path, 1024 * 1024);
    defer allocator.free(expected);

    const actual = try generateCaseSource(allocator, &loaded_case);
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
