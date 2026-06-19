//! Apply `inspect` name filters to collected declarations in place. Mirrors
//! Python's `apply_declaration_filters`: an include pattern keeps only matching
//! names, an exclude pattern drops matching names, applied per category in
//! declaration order. Patterns use the shared pattern matcher (anchors `^`/`$`,
//! alternation `|`, and substring match) rather than full regex.

const std = @import("std");
const declarations = @import("declarations.zig");
const ctype_resolver = @import("ctype_resolver.zig");

pub const Filters = struct {
    func_include: ?[]const u8 = null,
    func_exclude: ?[]const u8 = null,
    type_include: ?[]const u8 = null,
    type_exclude: ?[]const u8 = null,
    const_include: ?[]const u8 = null,
    const_exclude: ?[]const u8 = null,
    var_include: ?[]const u8 = null,
    var_exclude: ?[]const u8 = null,

    pub fn isEmpty(self: Filters) bool {
        return self.func_include == null and self.func_exclude == null and
            self.type_include == null and self.type_exclude == null and
            self.const_include == null and self.const_exclude == null and
            self.var_include == null and self.var_exclude == null;
    }
};

fn keepName(name: []const u8, include: ?[]const u8, exclude: ?[]const u8) bool {
    if (include) |pattern| {
        if (!ctype_resolver.functionNameMatchesPattern(name, pattern)) return false;
    }
    if (exclude) |pattern| {
        if (ctype_resolver.functionNameMatchesPattern(name, pattern)) return false;
    }
    return true;
}

fn filterCategory(
    comptime T: type,
    allocator: std.mem.Allocator,
    list: *std.ArrayListUnmanaged(T),
    include: ?[]const u8,
    exclude: ?[]const u8,
) void {
    if (include == null and exclude == null) return;
    var write: usize = 0;
    for (list.items) |item| {
        if (keepName(item.name, include, exclude)) {
            list.items[write] = item;
            write += 1;
        } else {
            item.deinit(allocator);
        }
    }
    list.shrinkRetainingCapacity(write);
}

/// Apply all configured filters to `decls` in place, freeing dropped entries.
pub fn apply(
    allocator: std.mem.Allocator,
    decls: *declarations.CollectedDeclarations,
    filters: Filters,
) void {
    filterCategory(declarations.FunctionDecl, allocator, &decls.functions, filters.func_include, filters.func_exclude);
    filterCategory(declarations.TypedefDecl, allocator, &decls.typedefs, filters.type_include, filters.type_exclude);
    filterCategory(declarations.ConstantDecl, allocator, &decls.constants, filters.const_include, filters.const_exclude);
    filterCategory(declarations.RuntimeVarDecl, allocator, &decls.runtime_vars, filters.var_include, filters.var_exclude);
    // Keep skipped-typedef reporting consistent with the surviving type set.
    filterCategory(declarations.SkippedTypedefDecl, allocator, &decls.skipped_typedefs, filters.type_include, filters.type_exclude);
}
