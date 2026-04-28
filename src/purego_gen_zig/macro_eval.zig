const std = @import("std");
const declarations = @import("declarations.zig");

pub fn normalizeMacroLiteralToken(token: []const u8) ?struct {
    literal: []const u8,
    is_unsigned: bool,
} {
    if (token.len == 0) return null;

    var end = token.len;
    while (end > 0) {
        const ch = token[end - 1];
        if (ch == 'u' or ch == 'U' or ch == 'l' or ch == 'L') {
            end -= 1;
            continue;
        }
        break;
    }
    const literal = token[0..end];
    if (literal.len == 0) return null;

    if (std.mem.startsWith(u8, literal, "0x") or std.mem.startsWith(u8, literal, "0X")) {
        _ = std.fmt.parseUnsigned(u64, literal[2..], 16) catch return null;
    } else {
        _ = std.fmt.parseUnsigned(u64, literal, 10) catch return null;
    }

    var is_unsigned = false;
    for (token[end..]) |ch| {
        if (ch == 'u' or ch == 'U') is_unsigned = true else if (ch != 'l' and ch != 'L') return null;
    }
    return .{ .literal = literal, .is_unsigned = is_unsigned };
}

const MacroOperator = enum {
    add,
    sub,
    mul,
    div,
    mod,
    shl,
    shr,
    bit_or,
    bit_and,
    bit_xor,
    unary_plus,
    unary_minus,
    bit_not,
};

fn macroOperatorPrecedence(op: MacroOperator) u8 {
    return switch (op) {
        .bit_or => 1,
        .bit_xor => 2,
        .bit_and => 3,
        .shl, .shr => 4,
        .add, .sub => 5,
        .mul, .div, .mod => 6,
        .unary_plus, .unary_minus, .bit_not => 7,
    };
}

fn isRightAssociative(op: MacroOperator) bool {
    return switch (op) {
        .unary_plus, .unary_minus, .bit_not => true,
        else => false,
    };
}

const MacroEvalState = struct {
    allocator: std.mem.Allocator,
    values: std.ArrayListUnmanaged(u64) = .empty,
    ops: std.ArrayListUnmanaged(union(enum) { lparen, op: MacroOperator }) = .empty,
    expect_operand: bool = true,

    fn deinit(self: *MacroEvalState) void {
        self.values.deinit(self.allocator);
        self.ops.deinit(self.allocator);
    }
};

fn truncSignedDivide(left: i64, right: i64) ?i64 {
    if (right == 0) return null;
    if (left == std.math.minInt(i64) and right == -1) return null;
    const negative = (left < 0) != (right < 0);
    const left_abs: u64 = if (left < 0) @intCast(-%left) else @intCast(left);
    const right_abs: u64 = if (right < 0) @intCast(-%right) else @intCast(right);
    const quotient = left_abs / right_abs;
    const quotient_i64: i64 = @intCast(quotient);
    return if (negative) -quotient_i64 else quotient_i64;
}

fn truncSignedMod(left: i64, right: i64) ?i64 {
    const quotient = truncSignedDivide(left, right) orelse return null;
    return left - (quotient * right);
}

fn bitcastI64(value: u64) i64 {
    return @bitCast(value);
}

fn bitcastU64(value: i64) u64 {
    return @bitCast(value);
}

fn applyMacroOperator(state: *MacroEvalState, op: MacroOperator) !bool {
    switch (op) {
        .unary_plus, .unary_minus, .bit_not => {
            if (state.values.items.len < 1) return false;
            const operand = state.values.items[state.values.items.len - 1];
            state.values.items.len -= 1;
            const operand_signed = bitcastI64(operand);
            const result = switch (op) {
                .unary_plus => operand,
                .unary_minus => bitcastU64(-%operand_signed),
                .bit_not => ~operand,
                else => unreachable,
            };
            try state.values.append(state.allocator, result);
        },
        else => {
            if (state.values.items.len < 2) return false;
            const right = state.values.items[state.values.items.len - 1];
            state.values.items.len -= 1;
            const left = state.values.items[state.values.items.len - 1];
            state.values.items.len -= 1;
            const left_signed = bitcastI64(left);
            const right_signed = bitcastI64(right);
            const result = switch (op) {
                .add => bitcastU64(left_signed +% right_signed),
                .sub => bitcastU64(left_signed -% right_signed),
                .mul => bitcastU64(left_signed *% right_signed),
                .div => blk: {
                    const value = truncSignedDivide(left_signed, right_signed) orelse return false;
                    break :blk bitcastU64(value);
                },
                .mod => blk: {
                    const value = truncSignedMod(left_signed, right_signed) orelse return false;
                    break :blk bitcastU64(value);
                },
                .shl => blk: {
                    if (right >= 64) return false;
                    break :blk left << @intCast(right);
                },
                .shr => blk: {
                    if (right >= 64) return false;
                    break :blk bitcastU64(left_signed >> @intCast(right));
                },
                .bit_or => left | right,
                .bit_and => left & right,
                .bit_xor => left ^ right,
                else => unreachable,
            };
            try state.values.append(state.allocator, result);
        },
    }
    return true;
}

fn pushMacroOperator(state: *MacroEvalState, op: MacroOperator) !bool {
    const precedence = macroOperatorPrecedence(op);
    while (state.ops.items.len > 0) {
        const top = state.ops.items[state.ops.items.len - 1];
        switch (top) {
            .lparen => break,
            .op => |top_op| {
                const top_precedence = macroOperatorPrecedence(top_op);
                if (top_precedence > precedence or (top_precedence == precedence and !isRightAssociative(op))) {
                    _ = state.ops.pop();
                    if (!try applyMacroOperator(state, top_op)) return false;
                    continue;
                }
                break;
            },
        }
    }
    try state.ops.append(state.allocator, .{ .op = op });
    return true;
}

fn parseMacroOperator(token: []const u8, expect_operand: bool) ?MacroOperator {
    if (std.mem.eql(u8, token, "+")) return if (expect_operand) .unary_plus else .add;
    if (std.mem.eql(u8, token, "-")) return if (expect_operand) .unary_minus else .sub;
    if (std.mem.eql(u8, token, "*")) return if (expect_operand) null else .mul;
    if (std.mem.eql(u8, token, "/")) return if (expect_operand) null else .div;
    if (std.mem.eql(u8, token, "%")) return if (expect_operand) null else .mod;
    if (std.mem.eql(u8, token, "<<")) return if (expect_operand) null else .shl;
    if (std.mem.eql(u8, token, ">>")) return if (expect_operand) null else .shr;
    if (std.mem.eql(u8, token, "|")) return if (expect_operand) null else .bit_or;
    if (std.mem.eql(u8, token, "&")) return if (expect_operand) null else .bit_and;
    if (std.mem.eql(u8, token, "^")) return if (expect_operand) null else .bit_xor;
    if (std.mem.eql(u8, token, "~")) return if (expect_operand) .bit_not else null;
    return null;
}

pub fn evaluateMacroExpression(
    allocator: std.mem.Allocator,
    tokens: []const []const u8,
    ctx: *const declarations.VisitorContext,
) !?u64 {
    var state = MacroEvalState{ .allocator = allocator };
    defer state.deinit();

    for (tokens) |token| {
        if (std.mem.eql(u8, token, "(")) {
            try state.ops.append(allocator, .lparen);
            state.expect_operand = true;
            continue;
        }
        if (std.mem.eql(u8, token, ")")) {
            var found_lparen = false;
            while (state.ops.items.len > 0) {
                const top = state.ops.items[state.ops.items.len - 1];
                state.ops.items.len -= 1;
                switch (top) {
                    .lparen => {
                        found_lparen = true;
                        break;
                    },
                    .op => |op| if (!try applyMacroOperator(&state, op)) return null,
                }
            }
            if (!found_lparen) return null;
            state.expect_operand = false;
            continue;
        }
        if (normalizeMacroLiteralToken(token)) |normalized| {
            const radix: u8 = if (std.mem.startsWith(u8, normalized.literal, "0x") or std.mem.startsWith(u8, normalized.literal, "0X")) 16 else 10;
            const digits = if (radix == 16) normalized.literal[2..] else normalized.literal;
            const value = std.fmt.parseUnsigned(u64, digits, radix) catch return null;
            try state.values.append(allocator, value);
            state.expect_operand = false;
            continue;
        }
        if (declarations.lookupKnownConstantValue(ctx, token)) |value| {
            try state.values.append(allocator, value);
            state.expect_operand = false;
            continue;
        }
        const op = parseMacroOperator(token, state.expect_operand) orelse return null;
        if (!try pushMacroOperator(&state, op)) return null;
        state.expect_operand = true;
    }

    if (state.expect_operand) return null;
    while (state.ops.items.len > 0) {
        const top = state.ops.items[state.ops.items.len - 1];
        state.ops.items.len -= 1;
        switch (top) {
            .lparen => return null,
            .op => |op| if (!try applyMacroOperator(&state, op)) return null,
        }
    }
    if (state.values.items.len != 1) return null;
    return state.values.items[0];
}

pub const TypedSentinelMacro = struct {
    value: u64,
    value_expr: []const u8,
    typed_go_type: []const u8,
};

pub fn parseUnsignedSentinelGoType(
    ctx: *const declarations.VisitorContext,
    tokens: []const []const u8,
    value: u64,
) !?[]const u8 {
    _ = value;
    var saw_unsigned_zero = false;
    var saw_minus = false;
    for (tokens) |token| {
        if (std.mem.eql(u8, token, "-")) {
            saw_minus = true;
            continue;
        }
        if (normalizeMacroLiteralToken(token)) |normalized| {
            if (normalized.is_unsigned and std.mem.eql(u8, normalized.literal, "0")) {
                saw_unsigned_zero = true;
            }
        }
    }
    if (!saw_unsigned_zero or !saw_minus) return null;
    return try ctx.decls.allocator.dupe(u8, "uint64");
}

pub fn parseTypedSentinelMacro(
    ctx: *const declarations.VisitorContext,
    tokens: []const []const u8,
) !?TypedSentinelMacro {
    var expr_buffer: std.ArrayList(u8) = .empty;
    defer expr_buffer.deinit(ctx.decls.allocator);
    for (tokens) |token| {
        try expr_buffer.appendSlice(ctx.decls.allocator, token);
    }
    const expr = expr_buffer.items;
    if (!std.mem.startsWith(u8, expr, "((") or !std.mem.endsWith(u8, expr, ")")) return null;

    const cast_end = std.mem.indexOfScalarPos(u8, expr, 2, ')') orelse return null;
    const type_name = expr[2..cast_end];
    if (type_name.len == 0) return null;

    const sentinel_expr = expr[cast_end + 1 .. expr.len - 1];
    if (std.mem.eql(u8, sentinel_expr, "0")) {
        return .{
            .value = 0,
            .value_expr = try ctx.decls.allocator.dupe(u8, "0"),
            .typed_go_type = try ctx.decls.allocator.dupe(u8, type_name),
        };
    }
    if (std.mem.eql(u8, sentinel_expr, "-1")) {
        return .{
            .value = std.math.maxInt(u64),
            .value_expr = try ctx.decls.allocator.dupe(u8, "^uintptr(0)"),
            .typed_go_type = try ctx.decls.allocator.dupe(u8, type_name),
        };
    }
    return null;
}
