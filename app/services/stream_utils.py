"""Utilities for cancellable streaming responses."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Generator
from typing import Any


class CancelToken:
    """A thread-safe token to signal cancellation across threads.

    When the ASGI server detects a client disconnect, it sets this token.
    The SSE generator checks the token on each iteration and breaks early.
    """

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()


def cancellable_stream(
    chunks: Any,
    cancel: CancelToken,
    *,
    on_cancel: Any = None,
) -> Generator[Any, None, None]:
    """Wrap an OpenAI Stream iterator so it can be cancelled mid-flight.

    Args:
        chunks: The OpenAI ``Stream`` object (or any iterable).
        cancel: A ``CancelToken`` checked after each yielded chunk.
        on_cancel: Optional callback invoked when cancellation is detected
                   (e.g. ``stream.close()`` to release the HTTP connection).

    Yields:
        Each item from *chunks* until the stream is exhausted or cancelled.
    """
    try:
        for chunk in chunks:
            if cancel.is_cancelled:
                break
            yield chunk
    finally:
        if on_cancel:
            try:
                on_cancel()
            except Exception:
                pass


async def watch_disconnect(request: Any, cancel: CancelToken) -> None:
    """ASGI helper: wait for the client to disconnect, then cancel the token."""
    try:
        while not cancel.is_cancelled:
            message = await request.receive()
            if message.get("type") == "http.disconnect":
                cancel.cancel()
                return
    except Exception:
        cancel.cancel()
