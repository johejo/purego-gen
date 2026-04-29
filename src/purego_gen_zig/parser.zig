const std = @import("std");
const clang = @import("clang.zig");
const c = clang.c;

pub const ParseError = error{
    IndexCreationFailed,
    TranslationUnitParseFailed,
    HasErrors,
};

pub const TranslationUnit = struct {
    index: c.CXIndex,
    tu: c.CXTranslationUnit,

    pub fn deinit(self: *TranslationUnit) void {
        c.clang_disposeTranslationUnit(self.tu);
        c.clang_disposeIndex(self.index);
    }

    pub fn cursor(self: *const TranslationUnit) c.CXCursor {
        return c.clang_getTranslationUnitCursor(self.tu);
    }
};

pub fn clangString(cx_str: c.CXString) []const u8 {
    const raw = c.clang_getCString(cx_str);
    if (raw) |ptr| {
        return std.mem.span(ptr);
    }
    return "";
}

pub fn visitChildren(
    comptime Ctx: type,
    comptime body: fn (ctx: *Ctx, cursor: c.CXCursor) anyerror!c.enum_CXChildVisitResult,
    parent: c.CXCursor,
    ctx: *Ctx,
) !void {
    const Wrapper = struct {
        ctx: *Ctx,
        err: ?anyerror = null,

        fn cb(cur: c.CXCursor, _: c.CXCursor, data: c.CXClientData) callconv(.c) c.enum_CXChildVisitResult {
            const w: *@This() = @ptrCast(@alignCast(data));
            if (w.err != null) return c.CXChildVisit_Break;
            return body(w.ctx, cur) catch |err| {
                w.err = err;
                return c.CXChildVisit_Break;
            };
        }
    };
    var w = Wrapper{ .ctx = ctx };
    _ = c.clang_visitChildren(parent, Wrapper.cb, @ptrCast(&w));
    if (w.err) |err| return err;
}

pub fn parseHeader(
    header_path: [:0]const u8,
    clang_args: []const [*:0]const u8,
) ParseError!TranslationUnit {
    const index = c.clang_createIndex(0, 0) orelse return ParseError.IndexCreationFailed;
    errdefer c.clang_disposeIndex(index);

    const options: c_uint = c.CXTranslationUnit_SkipFunctionBodies |
        c.CXTranslationUnit_DetailedPreprocessingRecord;

    const tu = c.clang_parseTranslationUnit(
        index,
        header_path.ptr,
        @ptrCast(clang_args.ptr),
        @intCast(clang_args.len),
        null,
        0,
        options,
    ) orelse return ParseError.TranslationUnitParseFailed;
    errdefer c.clang_disposeTranslationUnit(tu);

    // Check for fatal errors.
    const num_diag = c.clang_getNumDiagnostics(tu);
    var has_error = false;
    for (0..num_diag) |i| {
        const diag = c.clang_getDiagnostic(tu, @intCast(i));
        defer c.clang_disposeDiagnostic(diag);
        const severity = c.clang_getDiagnosticSeverity(diag);
        if (severity == c.CXDiagnostic_Error or severity == c.CXDiagnostic_Fatal) {
            const msg = c.clang_formatDiagnostic(diag, c.clang_defaultDiagnosticDisplayOptions());
            defer c.clang_disposeString(msg);
            const msg_str = clangString(msg);
            std.debug.print("clang error: {s}\n", .{msg_str});
            has_error = true;
        }
    }
    if (has_error) return ParseError.HasErrors;

    return TranslationUnit{ .index = index, .tu = tu };
}
