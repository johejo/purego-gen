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

    pub fn deinit(self: BufferParamPair, allocator: std.mem.Allocator) void {
        allocator.free(self.pointer);
        allocator.free(self.length);
    }
};

pub const ExplicitBufferParamHelper = struct {
    function_name: []const u8,
    pairs: []const BufferParamPair,

    pub fn deinit(self: ExplicitBufferParamHelper, allocator: std.mem.Allocator) void {
        allocator.free(self.function_name);
        for (self.pairs) |pair| pair.deinit(allocator);
        allocator.free(self.pairs);
    }
};

pub const PatternBufferParamHelper = struct {
    function_pattern: []const u8,

    pub fn deinit(self: PatternBufferParamHelper, allocator: std.mem.Allocator) void {
        allocator.free(self.function_pattern);
    }
};

pub const BufferParamHelper = union(enum) {
    explicit: ExplicitBufferParamHelper,
    pattern: PatternBufferParamHelper,

    pub fn deinit(self: BufferParamHelper, allocator: std.mem.Allocator) void {
        switch (self) {
            .explicit => |explicit| explicit.deinit(allocator),
            .pattern => |pattern| pattern.deinit(allocator),
        }
    }
};

pub const ExplicitCallbackParamHelper = struct {
    function_name: []const u8,
    params: []const []const u8,

    pub fn deinit(self: ExplicitCallbackParamHelper, allocator: std.mem.Allocator) void {
        allocator.free(self.function_name);
        for (self.params) |param| allocator.free(param);
        allocator.free(self.params);
    }
};

pub const OwnedStringReturnHelper = struct {
    function_name: []const u8,
    free_func_name: []const u8,

    pub fn deinit(self: OwnedStringReturnHelper, allocator: std.mem.Allocator) void {
        allocator.free(self.function_name);
        allocator.free(self.free_func_name);
    }
};

pub const PublicApiMatcher = union(enum) {
    exact: []const u8,
    pattern: []const u8,

    pub fn deinit(self: PublicApiMatcher, allocator: std.mem.Allocator) void {
        switch (self) {
            .exact => |value| allocator.free(value),
            .pattern => |value| allocator.free(value),
        }
    }
};

pub const PublicApiOverride = struct {
    source_name: []const u8,
    public_name: []const u8,

    pub fn deinit(self: PublicApiOverride, allocator: std.mem.Allocator) void {
        allocator.free(self.source_name);
        allocator.free(self.public_name);
    }
};

pub const PublicApiConfig = struct {
    strip_prefix: []const u8,
    type_aliases_include: []const PublicApiMatcher,
    type_aliases_overrides: []const PublicApiOverride,
    wrappers_include: []const PublicApiMatcher,
    wrappers_exclude: []const PublicApiMatcher,
    wrappers_overrides: []const PublicApiOverride,

    pub fn deinit(self: PublicApiConfig, allocator: std.mem.Allocator) void {
        allocator.free(self.strip_prefix);
        freeOwnedSlice(PublicApiMatcher, allocator, self.type_aliases_include);
        freeOwnedSlice(PublicApiOverride, allocator, self.type_aliases_overrides);
        freeOwnedSlice(PublicApiMatcher, allocator, self.wrappers_include);
        freeOwnedSlice(PublicApiMatcher, allocator, self.wrappers_exclude);
        freeOwnedSlice(PublicApiOverride, allocator, self.wrappers_overrides);
    }
};

fn freeOwnedSlice(comptime T: type, allocator: std.mem.Allocator, items: []const T) void {
    for (items) |item| item.deinit(allocator);
    allocator.free(items);
}

pub const NamingConfig = struct {
    type_prefix: []const u8,
    const_prefix: []const u8,
    func_prefix: []const u8,
    var_prefix: []const u8,
};

pub const ExcludeConfig = struct {
    func_names: []const []const u8,
    type_names: []const []const u8,
    const_names: []const []const u8,
    var_names: []const []const u8,
};

pub const IncludeConfig = struct {
    func_names: []const []const u8,
    type_names: []const []const u8,
    const_names: []const []const u8,
    var_names: []const []const u8,
};

fn freeStringSlice(allocator: std.mem.Allocator, items: []const []const u8) void {
    for (items) |item| allocator.free(item);
    allocator.free(items);
}

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
        freeStringSlice(allocator, self.include.func_names);
        freeStringSlice(allocator, self.include.type_names);
        freeStringSlice(allocator, self.include.const_names);
        freeStringSlice(allocator, self.include.var_names);
        freeStringSlice(allocator, self.exclude.func_names);
        freeStringSlice(allocator, self.exclude.type_names);
        freeStringSlice(allocator, self.exclude.const_names);
        freeStringSlice(allocator, self.exclude.var_names);
        freeOwnedSlice(BufferParamHelper, allocator, self.buffer_param_helpers);
        freeOwnedSlice(ExplicitCallbackParamHelper, allocator, self.callback_param_helpers);
        freeOwnedSlice(OwnedStringReturnHelper, allocator, self.owned_string_return_helpers);
        self.public_api.deinit(allocator);
    }
};
