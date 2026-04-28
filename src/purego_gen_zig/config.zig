const std = @import("std");

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
