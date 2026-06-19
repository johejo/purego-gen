const std = @import("std");
const go_generation = @import("go_generation.zig");
const config_load = @import("config_load.zig");
const text_diff = @import("text_diff.zig");

const supported_golden_case_ids = [_][]const u8{
    "abi_types",
    "auto_string_return",
    "basic_and_categories",
    "basic_func_type",
    "basic_type_strict_opaque",
    "bool_param",
    "buffer_input_helper",
    "buffer_input_multi_pair",
    "buffer_input_pattern",
    "buffer_wrapper_typedef_callback_passthrough",
    "by_value_records",
    "callback_auto_discover",
    "callback_param",
    "callback_param_conflict",
    "callback_param_dedup",
    "callback_param_multi",
    "callback_struct_opaque_ptr",
    "callback_typedef_complex_signature",
    "categories_const",
    "categories_mixed_filtered",
    "char_pointer_pointer_param",
    "comments_default",
    "comments_parse_all",
    "conditional_default",
    "conditional_with_define",
    "cross_header_strict_enum",
    "custom_prefix",
    "double_param",
    "double_pointer_param",
    "enum_bare_param_return",
    "enum_typedef_nonstrict_return",
    "exclude_only_basic",
    "float_param",
    "func_pointer_typedef_char_pp_param",
    "inline_func_pointer",
    "intptr_t_param",
    "libclang",
    "libsqlite3",
    "libzstd",
    "long_long_param",
    "long_long_typedef_param",
    "long_param",
    "macro_constants",
    "macro_sentinels",
    "non_callback_typedef",
    "opaque_func_only",
    "opaque_pointer_with_buffer_pair",
    "owned_string_return",
    "parameter_names",
    "pointer_to_int_param",
    "prefix_free",
    "public_api_basic",
    "runtime_smoke",
    "runtime_string",
    "short_param",
    "signed_char_param",
    "single_typedef_pointer_param",
    "strict_typing_default",
    "strict_typing_enabled",
    "struct_accessors_basic",
    "struct_array_pointer_mix",
    "typedef_chain_filtered_inner_int_param",
    "typedef_chain_int_param",
    "uintptr_t_param",
    "union_basic",
    "union_basic_accessors",
    "unsigned_char_param",
    "unsigned_int_return",
    "unsigned_long_param",
    "unsigned_short_param",
    "unsupported_typedef_uintptr_fallback",
    "void_callback",
};

// Cases intentionally skipped until the Zig generator supports more of the
// Python golden-case surface area.
const unsupported_golden_case_ids = [_][]const u8{};

pub const LoadedCase = struct {
    case_dir: []const u8,
    expected_path: []const u8,
    config: config_load.LoadedConfig,

    pub fn deinit(self: *LoadedCase, allocator: std.mem.Allocator) void {
        allocator.free(self.case_dir);
        allocator.free(self.expected_path);
        self.config.deinit(allocator);
    }
};

pub fn loadCaseFromDir(
    allocator: std.mem.Allocator,
    case_dir: []const u8,
) !LoadedCase {
    const config_path = try std.fs.path.join(allocator, &.{ case_dir, "config.json" });
    defer allocator.free(config_path);

    var config = try config_load.loadFromPath(allocator, config_path);
    errdefer config.deinit(allocator);

    const case_dir_owned = try allocator.dupe(u8, case_dir);
    errdefer allocator.free(case_dir_owned);

    const expected_path = try std.fs.path.join(allocator, &.{ case_dir, "generated.go" });

    return .{
        .case_dir = case_dir_owned,
        .expected_path = expected_path,
        .config = config,
    };
}

pub fn generateCaseSource(
    allocator: std.mem.Allocator,
    loaded_case: *const LoadedCase,
    skip_gofmt: bool,
) ![]u8 {
    return config_load.generateSource(allocator, &loaded_case.config, skip_gofmt);
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

    if (!std.mem.eql(u8, expected, actual)) {
        const case_id = std.fs.path.basename(case_dir);
        try text_diff.writeGoldenDiff(allocator, case_id, expected, actual);
        return error.TestExpectedEqual;
    }
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
