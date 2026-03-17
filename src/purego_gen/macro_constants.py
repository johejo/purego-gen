# Copyright (c) 2026 purego-gen contributors.

"""Macro constant evaluation helpers.

This module intentionally isolates token-based macro evaluation so parser
callers can switch to an alternative backend (for example, `clang -E -dM`)
without touching declaration walking logic.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INTEGER_LITERAL_WITH_SUFFIX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<literal>(?:0[xX][0-9A-Fa-f]+)|(?:[1-9][0-9]*)|0)(?P<suffix>[uUlL]*)$"
)
_ALLOWED_MACRO_OPERATOR_TOKENS: Final[frozenset[str]] = frozenset({
    "+",
    "-",
    "*",
    "/",
    "%",
    "<<",
    ">>",
    "|",
    "&",
    "^",
    "~",
    "(",
    ")",
})
_MACRO_MIN_OBJECT_LIKE_TOKEN_COUNT: Final[int] = 2
_CASTED_SENTINEL_MACRO_MIN_TOKEN_COUNT: Final[int] = 6
_UNSIGNED_WRAP_BITS: Final[int] = 64

_BINARY_OPERATOR_HANDLERS: Final[dict[type[ast.operator], Callable[[int, int], int]]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}


@dataclass(frozen=True, slots=True)
class EvaluatedMacroConstant:
    """Evaluated object-like macro constant payload."""

    value: int
    c_type: str | None = None
    go_expression: str | None = None


def _normalize_macro_literal_token(token: str) -> tuple[str, bool] | None:
    """Normalize one C integer literal token into Python-compatible form.

    Returns:
        Tuple of normalized literal token and unsigned-suffix flag, or `None` if unsupported.
    """
    match = _INTEGER_LITERAL_WITH_SUFFIX_PATTERN.fullmatch(token)
    if match is None:
        return None
    suffix = match.group("suffix")
    return match.group("literal"), ("u" in suffix.lower())


def _build_macro_expression(
    *,
    expression_tokens: tuple[str, ...],
    known_constant_values: Mapping[str, int],
) -> tuple[str, bool] | None:
    """Build a Python-evaluable integer expression from macro tokens.

    Returns:
        Normalized expression string, or `None` when unsupported tokens exist.
    """
    normalized_tokens: list[str] = []
    has_unsigned_literal = False
    for macro_piece in expression_tokens:
        if macro_piece in _ALLOWED_MACRO_OPERATOR_TOKENS:
            normalized_tokens.append(macro_piece)
            continue
        normalized_literal = _normalize_macro_literal_token(macro_piece)
        if normalized_literal is not None:
            literal_text, literal_is_unsigned = normalized_literal
            normalized_tokens.append(literal_text)
            has_unsigned_literal = has_unsigned_literal or literal_is_unsigned
            continue
        if _IDENTIFIER_PATTERN.fullmatch(macro_piece) is not None:
            resolved = known_constant_values.get(macro_piece)
            if resolved is None:
                return None
            normalized_tokens.append(str(resolved))
            continue
        return None

    if not normalized_tokens:
        return None
    return " ".join(normalized_tokens), has_unsigned_literal


def _evaluate_unary_integer_operator(op: ast.unaryop, operand: int) -> int | None:
    """Evaluate one unary operator for integer-only expression support.

    Returns:
        Evaluated integer value, or `None` when operator is unsupported.
    """
    if isinstance(op, ast.UAdd):
        return operand
    if isinstance(op, ast.USub):
        return -operand
    if isinstance(op, ast.Invert):
        return ~operand
    return None


def _evaluate_binary_integer_operator(op: ast.operator, left: int, right: int) -> int | None:
    """Evaluate one binary operator for integer-only expression support.

    Returns:
        Evaluated integer value, or `None` when operator/input is unsupported.
    """
    if isinstance(op, ast.Div):
        if right == 0:
            return None
        sign = -1 if (left < 0) ^ (right < 0) else 1
        return sign * (abs(left) // abs(right))
    if isinstance(op, ast.Mod):
        if right == 0:
            return None
        return left % right
    handler = _BINARY_OPERATOR_HANDLERS.get(type(op))
    if handler is None:
        return None
    return handler(left, right)


def _evaluate_integer_expression_ast(node: ast.AST) -> int | None:
    """Evaluate restricted Python AST node as integer expression.

    Returns:
        Evaluated integer value, or `None` when node/operator is unsupported.
    """
    result: int | None = None
    if isinstance(node, ast.Expression):
        result = _evaluate_integer_expression_ast(node.body)
    elif isinstance(node, ast.Constant) and isinstance(node.value, int):
        result = int(node.value)
    elif isinstance(node, ast.UnaryOp):
        operand = _evaluate_integer_expression_ast(node.operand)
        if operand is None:
            return None
        result = _evaluate_unary_integer_operator(node.op, operand)
    elif isinstance(node, ast.BinOp):
        left = _evaluate_integer_expression_ast(node.left)
        right = _evaluate_integer_expression_ast(node.right)
        if left is None or right is None:
            return None
        result = _evaluate_binary_integer_operator(node.op, left, right)
    return result


def _evaluate_c_integer_expression(expression: str) -> int | None:
    """Evaluate integer-only expression with a C-like operator subset.

    Returns:
        Evaluated integer value, or `None` if expression is unsupported.
    """
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None
    return _evaluate_integer_expression_ast(parsed)


def _evaluate_casted_sentinel_macro_definition(
    *,
    expression_tokens: tuple[str, ...],
) -> EvaluatedMacroConstant | None:
    """Evaluate one narrowly-supported casted sentinel macro definition.

    Supported forms are limited to object-like macros shaped like:
    `((typedef_name)0)` and `((typedef_name)-1)`.

    Returns:
        Evaluated macro payload when the token sequence matches one supported
        casted sentinel form, otherwise `None`.
    """
    if (
        len(expression_tokens) < _CASTED_SENTINEL_MACRO_MIN_TOKEN_COUNT
        or expression_tokens[:2] != ("(", "(")
        or expression_tokens[-1] != ")"
    ):
        return None

    try:
        type_close_index = expression_tokens.index(")", 2)
    except ValueError:
        return None
    type_tokens = expression_tokens[2:type_close_index]
    if len(type_tokens) != 1:
        return None
    c_type = type_tokens[0]
    if _IDENTIFIER_PATTERN.fullmatch(c_type) is None:
        return None

    cast_value_tokens = expression_tokens[type_close_index + 1 : -1]
    result: EvaluatedMacroConstant | None = None
    if cast_value_tokens == ("0",):
        result = EvaluatedMacroConstant(value=0, c_type=c_type)
    elif cast_value_tokens == ("-", "1"):
        result = EvaluatedMacroConstant(
            value=(1 << _UNSIGNED_WRAP_BITS) - 1,
            c_type=c_type,
            go_expression="^uintptr(0)",
        )
    return result


def evaluate_object_like_macro_definition(
    *,
    token_spellings: tuple[str, ...],
    known_constant_values: Mapping[str, int],
    is_function_like: bool,
) -> EvaluatedMacroConstant | None:
    """Evaluate one macro definition as an integer constant when supported.

    Args:
        token_spellings: Macro token sequence including the macro name token.
        known_constant_values: Already-resolved constant values usable as references.
        is_function_like: Externally-resolved function-like classification.

    Returns:
        Evaluated macro payload for supported object-like macro definitions,
        otherwise `None`.
    """
    if not token_spellings or len(token_spellings) < _MACRO_MIN_OBJECT_LIKE_TOKEN_COUNT:
        return None
    if is_function_like:
        return None

    casted_sentinel = _evaluate_casted_sentinel_macro_definition(
        expression_tokens=token_spellings[1:],
    )
    if casted_sentinel is not None:
        return casted_sentinel

    expression = _build_macro_expression(
        expression_tokens=token_spellings[1:],
        known_constant_values=known_constant_values,
    )
    if expression is None:
        return None
    expression_text, has_unsigned_literal = expression

    evaluated = _evaluate_c_integer_expression(expression_text)
    if evaluated is None:
        return None
    if has_unsigned_literal and evaluated < 0:
        evaluated %= 1 << _UNSIGNED_WRAP_BITS
    return EvaluatedMacroConstant(value=evaluated)
