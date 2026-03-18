# Copyright (c) 2026 purego-gen contributors.

"""Normalization helpers for generator helper configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from purego_gen.config_model import (
    BufferInputHelper,
    BufferInputPair,
    CallbackInputHelper,
    GeneratorHelpers,
    HeaderOverlay,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from purego_gen.config_schema import (
        BufferInputHelperInput,
        BufferInputPairInput,
        CallbackInputHelperInput,
        HeaderOverlayInput,
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
