# Copyright (c) 2026 purego-gen contributors.

"""Normalization helpers for generator helper configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from purego_gen.config_model import (
    BufferInputHelper,
    BufferInputPair,
    BufferInputPatternHelper,
    CallbackInputHelper,
    GeneratorHelpers,
    HeaderOverlay,
    NullableStringInputHelper,
    OutputStringParamHelper,
    OwnedStringReturnHelper,
    OwnedStringReturnPatternHelper,
)
from purego_gen.config_schema import (
    BufferInputHelperInput,
    BufferInputPatternHelperInput,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from purego_gen.config_schema import (
        BufferInputPairInput,
        CallbackInputHelperInput,
        HeaderOverlayInput,
        HelpersInput,
        NullableStringInputHelperInput,
        OutputStringParamHelperInput,
        OwnedStringReturnHelperInput,
    )


def normalize_generator_helpers(helpers: HelpersInput) -> GeneratorHelpers:
    """Normalize helper config inputs into execution-ready helper models.

    Returns:
        Normalized helper config ready for rendering.
    """
    return GeneratorHelpers(
        auto_callback_inputs=bool(helpers.auto_callback_inputs),
        buffer_inputs=_normalize_buffer_inputs(helpers.buffer_inputs),
        callback_inputs=_normalize_optional_items(
            helpers.callback_inputs,
            _normalize_callback_input_helper,
        ),
        owned_string_returns=_normalize_optional_items(
            helpers.owned_string_returns,
            _normalize_owned_string_return_helper,
        ),
        nullable_string_inputs=_normalize_optional_items(
            helpers.nullable_string_inputs,
            _normalize_nullable_string_input_helper,
        ),
        output_string_params=_normalize_optional_items(
            helpers.output_string_params,
            _normalize_output_string_param_helper,
        ),
    )


def _normalize_optional_items[InputT, OutputT](
    raw_items: tuple[InputT, ...] | None,
    normalize_item: Callable[[InputT], OutputT],
) -> tuple[OutputT, ...]:
    if raw_items is None:
        return ()
    return tuple(normalize_item(item) for item in raw_items)


def _normalize_buffer_inputs(
    raw_items: tuple[BufferInputHelperInput | BufferInputPatternHelperInput, ...] | None,
) -> tuple[BufferInputHelper | BufferInputPatternHelper, ...]:
    if raw_items is None:
        return ()
    results: list[BufferInputHelper | BufferInputPatternHelper] = []
    for item in raw_items:
        if isinstance(item, BufferInputPatternHelperInput):
            results.append(_normalize_buffer_input_pattern_helper(item))
        else:
            results.append(_normalize_buffer_input_helper(item))
    return tuple(results)


def _normalize_buffer_input_pair(pair: BufferInputPairInput) -> BufferInputPair:
    return BufferInputPair(pointer=pair.pointer, length=pair.length)


def _normalize_buffer_input_helper(helper: BufferInputHelperInput) -> BufferInputHelper:
    return BufferInputHelper(
        function=helper.function,
        pairs=tuple(_normalize_buffer_input_pair(pair) for pair in helper.pairs),
    )


def _normalize_buffer_input_pattern_helper(
    helper: BufferInputPatternHelperInput,
) -> BufferInputPatternHelper:
    return BufferInputPatternHelper(function_pattern=helper.function_pattern)


def _normalize_callback_input_helper(helper: CallbackInputHelperInput) -> CallbackInputHelper:
    return CallbackInputHelper(function=helper.function, parameters=helper.parameters)


def _normalize_owned_string_return_helper(
    helper: OwnedStringReturnHelperInput,
) -> OwnedStringReturnHelper | OwnedStringReturnPatternHelper:
    if helper.function is not None:
        return OwnedStringReturnHelper(function=helper.function, free_func=helper.free_func)
    # model_validator guarantees function_pattern is not None here; `or ""` narrows the type.
    function_pattern: str = helper.function_pattern or ""
    return OwnedStringReturnPatternHelper(
        function_pattern=function_pattern,
        free_func=helper.free_func,
    )


def normalize_header_overlays(
    raw_items: tuple[HeaderOverlayInput, ...] | None,
) -> tuple[HeaderOverlay, ...]:
    """Normalize optional in-memory header overlays.

    Returns:
        Normalized overlays ready for generator resolution.

    Raises:
        RuntimeError: Overlay paths are duplicated.
    """
    overlays = _normalize_optional_items(raw_items, _normalize_header_overlay)
    seen_paths: set[str] = set()
    for overlay in overlays:
        if overlay.path in seen_paths:
            message = f"duplicate overlay path: {overlay.path}"
            raise RuntimeError(message)
        seen_paths.add(overlay.path)
    return overlays


def _normalize_nullable_string_input_helper(
    helper: NullableStringInputHelperInput,
) -> NullableStringInputHelper:
    return NullableStringInputHelper(function=helper.function, parameters=helper.parameters)


def _normalize_output_string_param_helper(
    helper: OutputStringParamHelperInput,
) -> OutputStringParamHelper:
    return OutputStringParamHelper(function=helper.function, parameters=helper.parameters)


def _normalize_header_overlay(overlay: HeaderOverlayInput) -> HeaderOverlay:
    return HeaderOverlay(path=overlay.path, content=overlay.content)
