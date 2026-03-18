# Copyright (c) 2026 purego-gen contributors.

"""Normalization helpers for generator helper configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from purego_gen.config_model import (
    BufferInputHelper,
    BufferInputPair,
    CallbackInputHelper,
    GeneratorHelpers,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from purego_gen.config_schema import (
        BufferInputHelperInput,
        BufferInputPairInput,
        CallbackInputHelperInput,
        HelpersInput,
    )


def normalize_generator_helpers(helpers: HelpersInput) -> GeneratorHelpers:
    """Normalize helper config inputs into execution-ready helper models.

    Returns:
        Normalized helper config ready for rendering.
    """
    return GeneratorHelpers(
        buffer_inputs=_normalize_optional_items(
            helpers.buffer_inputs,
            _normalize_buffer_input_helper,
        ),
        callback_inputs=_normalize_optional_items(
            helpers.callback_inputs,
            _normalize_callback_input_helper,
        ),
    )


def _normalize_optional_items[InputT, OutputT](
    raw_items: tuple[InputT, ...] | None,
    normalize_item: Callable[[InputT], OutputT],
) -> tuple[OutputT, ...]:
    if raw_items is None:
        return ()
    return tuple(normalize_item(item) for item in raw_items)


def _normalize_buffer_input_pair(pair: BufferInputPairInput) -> BufferInputPair:
    return BufferInputPair(pointer=pair.pointer, length=pair.length)


def _normalize_buffer_input_helper(helper: BufferInputHelperInput) -> BufferInputHelper:
    return BufferInputHelper(
        function=helper.function,
        pairs=tuple(_normalize_buffer_input_pair(pair) for pair in helper.pairs),
    )


def _normalize_callback_input_helper(helper: CallbackInputHelperInput) -> CallbackInputHelper:
    return CallbackInputHelper(function=helper.function, parameters=helper.parameters)
