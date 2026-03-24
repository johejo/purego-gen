# Copyright (c) 2026 purego-gen contributors.

"""Normalization helpers for generator helper configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from purego_gen.config_model import (
    BufferInputPair,
    BufferParamHelper,
    BufferParamPatternHelper,
    CallbackParamHelper,
    GeneratorHelpers,
    HeaderOverlay,
    NullableStringParamHelper,
    OutputStringParamHelper,
    OwnedStringReturnHelper,
    OwnedStringReturnPatternHelper,
)
from purego_gen.config_schema import BufferParamPatternHelperInput, PatternInput

if TYPE_CHECKING:
    from collections.abc import Callable

    from purego_gen.config_schema import (
        BufferInputPairInput,
        BufferParamHelperInput,
        CallbackParamHelperInput,
        HeaderOverlayInput,
        HelpersInput,
        NullableStringParamHelperInput,
        OutputStringParamHelperInput,
        OwnedStringReturnHelperInput,
    )


def normalize_generator_helpers(
    helpers: HelpersInput,
    *,
    auto_callbacks: bool = False,
) -> GeneratorHelpers:
    """Normalize helper config inputs into execution-ready helper models.

    Returns:
        Normalized helper config ready for rendering.
    """
    return GeneratorHelpers(
        auto_callbacks=auto_callbacks,
        buffer_params=_normalize_buffer_params(helpers.buffer_params),
        callback_params=_normalize_optional_items(
            helpers.callback_params,
            _normalize_callback_param_helper,
        ),
        owned_string_returns=_normalize_optional_items(
            helpers.owned_string_returns,
            _normalize_owned_string_return_helper,
        ),
        nullable_string_params=_normalize_optional_items(
            helpers.nullable_string_params,
            _normalize_nullable_string_param_helper,
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


def _normalize_buffer_input_pair(pair: BufferInputPairInput) -> BufferInputPair:
    return BufferInputPair(pointer=pair.pointer, length=pair.length)


def _normalize_buffer_params(
    raw_items: tuple[BufferParamHelperInput | BufferParamPatternHelperInput, ...] | None,
) -> tuple[BufferParamHelper | BufferParamPatternHelper, ...]:
    if raw_items is None:
        return ()
    results: list[BufferParamHelper | BufferParamPatternHelper] = []
    for item in raw_items:
        if isinstance(item, BufferParamPatternHelperInput):
            results.append(BufferParamPatternHelper(function_pattern=item.function.pattern))
        else:
            results.append(
                BufferParamHelper(
                    function=item.function,
                    pairs=tuple(_normalize_buffer_input_pair(p) for p in item.pairs),
                )
            )
    return tuple(results)


def _normalize_callback_param_helper(
    helper: CallbackParamHelperInput,
) -> CallbackParamHelper:
    return CallbackParamHelper(function=helper.function, params=helper.params)


def _normalize_owned_string_return_helper(
    helper: OwnedStringReturnHelperInput,
) -> OwnedStringReturnHelper | OwnedStringReturnPatternHelper:
    if isinstance(helper.function, PatternInput):
        return OwnedStringReturnPatternHelper(
            function_pattern=helper.function.pattern,
            free_func=helper.free_func,
        )
    return OwnedStringReturnHelper(function=helper.function, free_func=helper.free_func)


def _normalize_nullable_string_param_helper(
    helper: NullableStringParamHelperInput,
) -> NullableStringParamHelper:
    return NullableStringParamHelper(function=helper.function, params=helper.params)


def _normalize_output_string_param_helper(
    helper: OutputStringParamHelperInput,
) -> OutputStringParamHelper:
    return OutputStringParamHelper(function=helper.function, params=helper.params)


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


def _normalize_header_overlay(overlay: HeaderOverlayInput) -> HeaderOverlay:
    return HeaderOverlay(path=overlay.path, content=overlay.content)
