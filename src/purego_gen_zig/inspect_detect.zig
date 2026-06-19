//! Config-independent signature scanning used by `inspect` to surface helper
//! candidates. Mirrors the detection logic in Python's `helper_rendering.py`
//! (`find_callback_candidates`, `find_buffer_candidates`,
//! `detect_callback_registration_patterns`). All returned slices borrow string
//! data from the passed `CollectedDeclarations`; allocate the outer slices with
//! an arena so callers need not free them individually.

const std = @import("std");
const declarations = @import("declarations.zig");

pub const ParamRef = struct {
    name: []const u8,
    c_type: []const u8,
};

pub const CallbackCandidate = struct {
    function: []const u8,
    params: []const ParamRef,
};

pub const BufferPair = struct {
    pointer: []const u8,
    length: []const u8,
};

pub const BufferCandidate = struct {
    function: []const u8,
    pairs: []const BufferPair,
};

pub const RegistrationPattern = struct {
    function: []const u8,
    callback_param: []const u8,
    userdata_param: ?[]const u8,
    destructor_param: ?[]const u8,
};

const c_type_qualifiers = std.StaticStringMap(void).initComptime(.{
    .{ "const", {} },
    .{ "volatile", {} },
    .{ "restrict", {} },
});

const userdata_names = std.StaticStringMap(void).initComptime(.{
    .{ "user_data", {} },
    .{ "userdata", {} },
    .{ "userData", {} },
    .{ "data", {} },
    .{ "ctx", {} },
    .{ "context", {} },
    .{ "arg", {} },
    .{ "closure", {} },
    .{ "extra", {} },
    .{ "info", {} },
    .{ "pCtx", {} },
    .{ "pArg", {} },
});

const destructor_names = [_][]const u8{
    "destroy",
    "destructor",
    "free",
    "release",
    "cleanup",
    "dtor",
    "dispose",
    "finalize",
    "xdestroy",
    "xdelete",
};

/// C types that map to a Go integer in `_BUFFER_HELPER_LENGTH_GO_TYPES`.
fn isIntegerLengthType(c_type: []const u8) bool {
    const set = std.StaticStringMap(void).initComptime(.{
        .{ "int", {} },
        .{ "unsigned int", {} },
        .{ "long", {} },
        .{ "unsigned long", {} },
        .{ "long long", {} },
        .{ "unsigned long long", {} },
        .{ "int32_t", {} },
        .{ "uint32_t", {} },
        .{ "int64_t", {} },
        .{ "uint64_t", {} },
        .{ "uintptr_t", {} },
        .{ "intptr_t", {} },
    });
    var buf: [64]u8 = undefined;
    const normalized = normalizeInto(&buf, c_type) orelse return false;
    return set.has(normalized);
}

/// A pointer C type renders to Go `uintptr`, which is an accepted buffer length
/// type. Mirrors Python's reliance on resolved `go_parameter_types`.
fn endsWithStar(text: []const u8) bool {
    var end = text.len;
    while (end > 0 and (text[end - 1] == ' ' or text[end - 1] == '\t')) end -= 1;
    return end > 0 and text[end - 1] == '*';
}

fn isPointerType(c_type: []const u8) bool {
    if (isFunctionPointerCType(c_type)) return true;
    var buf: [128]u8 = undefined;
    // Normalized output is single-spaced; fall back to the raw spelling when it
    // is too long to normalize cheaply.
    const candidate = normalizeInto(&buf, c_type) orelse c_type;
    return endsWithStar(candidate);
}

/// Whether a parameter can serve as a buffer length: a recognized integer type
/// or any pointer (both render to a Go length type), resolving one typedef hop.
fn isBufferLengthType(decls: *const declarations.CollectedDeclarations, c_type: []const u8) bool {
    if (isIntegerLengthType(c_type) or isPointerType(c_type)) return true;
    for (decls.typedefs.items) |td| {
        if (ctypeNormEql(td.name, c_type)) {
            if (isIntegerLengthType(td.c_type) or isPointerType(td.c_type)) return true;
        }
    }
    return false;
}

/// Detect a function-pointer declarator (`(*)`, with optional surrounding
/// whitespace) anywhere in the spelling. Qualifiers do not introduce these
/// tokens, so the raw spelling can be scanned without normalization.
pub fn isFunctionPointerCType(c_type: []const u8) bool {
    var i: usize = 0;
    while (i < c_type.len) : (i += 1) {
        if (c_type[i] != '(') continue;
        var j = i + 1;
        while (j < c_type.len and c_type[j] == ' ') j += 1;
        if (j >= c_type.len or c_type[j] != '*') continue;
        j += 1;
        while (j < c_type.len and c_type[j] == ' ') j += 1;
        if (j < c_type.len and c_type[j] == ')') return true;
    }
    return false;
}

/// Write the qualifier-stripped, single-spaced normalization of `c_type` into
/// `buf`. Returns null when it does not fit (caller treats as no-match).
fn normalizeInto(buf: []u8, c_type: []const u8) ?[]const u8 {
    var len: usize = 0;
    var it = std.mem.tokenizeAny(u8, c_type, " \t\n\r");
    while (it.next()) |token| {
        if (c_type_qualifiers.has(token)) continue;
        if (len != 0) {
            if (len >= buf.len) return null;
            buf[len] = ' ';
            len += 1;
        }
        if (len + token.len > buf.len) return null;
        @memcpy(buf[len .. len + token.len], token);
        len += token.len;
    }
    return buf[0..len];
}

/// Compare two C-type spellings ignoring qualifiers and whitespace differences.
fn ctypeNormEql(a: []const u8, b: []const u8) bool {
    var a_it = qualifierStrippedTokens(a);
    var b_it = qualifierStrippedTokens(b);
    while (true) {
        const a_tok = a_it.next();
        const b_tok = b_it.next();
        if (a_tok == null and b_tok == null) return true;
        if (a_tok == null or b_tok == null) return false;
        if (!std.mem.eql(u8, a_tok.?, b_tok.?)) return false;
    }
}

const QualifierStrippedTokens = struct {
    inner: std.mem.TokenIterator(u8, .any),

    fn next(self: *QualifierStrippedTokens) ?[]const u8 {
        while (self.inner.next()) |token| {
            if (c_type_qualifiers.has(token)) continue;
            return token;
        }
        return null;
    }
};

fn qualifierStrippedTokens(c_type: []const u8) QualifierStrippedTokens {
    return .{ .inner = std.mem.tokenizeAny(u8, c_type, " \t\n\r") };
}

/// Resolve a parameter C type to whether it (or a single typedef hop) is a
/// function pointer.
fn resolvesToFunctionPointer(decls: *const declarations.CollectedDeclarations, c_type: []const u8) bool {
    if (isFunctionPointerCType(c_type)) return true;
    for (decls.typedefs.items) |td| {
        if (ctypeNormEql(td.name, c_type) or ctypeNormEql(td.c_type, c_type)) {
            if (isFunctionPointerCType(td.c_type)) return true;
        }
    }
    return false;
}

fn isVoidPointer(c_type: []const u8) bool {
    var buf: [64]u8 = undefined;
    const normalized = normalizeInto(&buf, c_type) orelse return false;
    return std.mem.eql(u8, normalized, "void *");
}

fn isDestructorName(name: []const u8) bool {
    var lower_buf: [128]u8 = undefined;
    if (name.len > lower_buf.len) return false;
    const lower = std.ascii.lowerString(lower_buf[0..name.len], name);
    for (destructor_names) |needle| {
        if (std.mem.indexOf(u8, lower, needle) != null) return true;
    }
    return false;
}

/// Find functions with at least one function-pointer parameter.
pub fn findCallbackCandidates(
    arena: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]CallbackCandidate {
    var candidates: std.ArrayListUnmanaged(CallbackCandidate) = .empty;
    for (decls.functions.items) |func| {
        var matching: std.ArrayListUnmanaged(ParamRef) = .empty;
        for (func.parameter_names, func.parameter_c_types) |name, c_type| {
            if (resolvesToFunctionPointer(decls, c_type)) {
                try matching.append(arena, .{ .name = name, .c_type = c_type });
            }
        }
        if (matching.items.len > 0) {
            try candidates.append(arena, .{
                .function = func.name,
                .params = try matching.toOwnedSlice(arena),
            });
        }
    }
    return candidates.toOwnedSlice(arena);
}

/// Find functions with consecutive `(void *, length)` parameter pairs.
pub fn findBufferCandidates(
    arena: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]BufferCandidate {
    var candidates: std.ArrayListUnmanaged(BufferCandidate) = .empty;
    for (decls.functions.items) |func| {
        var pairs: std.ArrayListUnmanaged(BufferPair) = .empty;
        const names = func.parameter_names;
        const c_types = func.parameter_c_types;
        var i: usize = 0;
        while (i + 1 < names.len) {
            if (isVoidPointer(c_types[i]) and isBufferLengthType(decls, c_types[i + 1])) {
                try pairs.append(arena, .{ .pointer = names[i], .length = names[i + 1] });
                i += 2;
            } else {
                i += 1;
            }
        }
        if (pairs.items.len > 0) {
            try candidates.append(arena, .{
                .function = func.name,
                .pairs = try pairs.toOwnedSlice(arena),
            });
        }
    }
    return candidates.toOwnedSlice(arena);
}

fn cTypeForParam(func: declarations.FunctionDecl, name: []const u8) ?[]const u8 {
    for (func.parameter_names, func.parameter_c_types) |param_name, c_type| {
        if (std.mem.eql(u8, param_name, name)) return c_type;
    }
    return null;
}

fn findUserdataNeighbor(func: declarations.FunctionDecl, callback_name: []const u8) ?[]const u8 {
    for (func.parameter_names, func.parameter_c_types) |name, c_type| {
        if (std.mem.eql(u8, name, callback_name)) continue;
        if (isVoidPointer(c_type) and userdata_names.has(name)) return name;
    }
    return null;
}

fn isCallbackParam(params: []const ParamRef, name: []const u8) bool {
    for (params) |param| {
        if (std.mem.eql(u8, param.name, name)) return true;
    }
    return false;
}

fn findDestructorNeighbor(
    decls: *const declarations.CollectedDeclarations,
    func: declarations.FunctionDecl,
    callback_name: []const u8,
    callback_params: []const ParamRef,
) ?[]const u8 {
    // First prefer another callback-typed parameter whose name looks like a
    // destructor.
    for (func.parameter_names) |name| {
        if (std.mem.eql(u8, name, callback_name)) continue;
        if (!isCallbackParam(callback_params, name)) continue;
        if (isDestructorName(name)) return name;
    }
    // Otherwise any destructor-named parameter that resolves to a function
    // pointer.
    for (func.parameter_names) |name| {
        if (std.mem.eql(u8, name, callback_name)) continue;
        if (isCallbackParam(callback_params, name)) continue;
        if (!isDestructorName(name)) continue;
        const c_type = cTypeForParam(func, name) orelse continue;
        if (resolvesToFunctionPointer(decls, c_type)) return name;
    }
    return null;
}

fn functionByName(decls: *const declarations.CollectedDeclarations, name: []const u8) ?declarations.FunctionDecl {
    for (decls.functions.items) |func| {
        if (std.mem.eql(u8, func.name, name)) return func;
    }
    return null;
}

/// Detect `(callback, userdata, destructor)` triples in function signatures.
pub fn detectRegistrationPatterns(
    arena: std.mem.Allocator,
    decls: *const declarations.CollectedDeclarations,
) ![]RegistrationPattern {
    const candidates = try findCallbackCandidates(arena, decls);
    var patterns: std.ArrayListUnmanaged(RegistrationPattern) = .empty;
    for (candidates) |candidate| {
        const func = functionByName(decls, candidate.function) orelse continue;
        for (candidate.params) |cb_param| {
            const cb_name = cb_param.name;
            const userdata = findUserdataNeighbor(func, cb_name);
            const destructor = findDestructorNeighbor(decls, func, cb_name, candidate.params);
            if (userdata != null or destructor != null) {
                try patterns.append(arena, .{
                    .function = candidate.function,
                    .callback_param = cb_name,
                    .userdata_param = userdata,
                    .destructor_param = destructor,
                });
            }
        }
    }
    return patterns.toOwnedSlice(arena);
}
