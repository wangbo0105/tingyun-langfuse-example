"""
Langfuse SDK compatibility layer for v2.x ~ v4.x.

Provides a unified API surface that adapts to whichever langfuse version is installed:
- v2 (≤2.x): Uses Langfuse() + trace()/span()/generation() pattern
- v3 early (3.0.x): Uses get_client() + start_as_current_span/generation (no unified observation API)
- v3 later (≥3.1): Uses get_client() + start_as_current_observation() pattern
- v4 (≥4.0): Same as later v3, with minor differences handled transparently

Usage:
    from app.langfuse_compat import get_langfuse, get_openai_client
"""

from __future__ import annotations

import contextvars as _cv
import logging
from contextlib import contextmanager
from typing import Any

import langfuse as _langfuse_module

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------
def _detect_version() -> str:
    """Detect langfuse version from module attr or importlib.metadata."""
    # v2.x and early v3 expose __version__
    if hasattr(_langfuse_module, "__version__"):
        return _langfuse_module.__version__
    # Later v3 / v4 removed __version__; fall back to metadata
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("langfuse")
    except Exception:
        return "0.0.0"


_VERSION_STR: str = _detect_version()
_VERSION_TUPLE: tuple[int, ...] = tuple(
    int(x) for x in _VERSION_STR.split(".")[:2]
)
MAJOR: int = _VERSION_TUPLE[0] if _VERSION_TUPLE else 0
MINOR: int = _VERSION_TUPLE[1] if len(_VERSION_TUPLE) > 1 else 0
IS_V2: bool = MAJOR < 3
IS_V3: bool = MAJOR == 3
IS_V4: bool = MAJOR >= 4

logger.info("langfuse_compat: detected langfuse %s (major=%d)", _VERSION_STR, MAJOR)


# ---------------------------------------------------------------------------
# Observation wrapper for v2 compatibility
# ---------------------------------------------------------------------------
class _V2ObservationWrapper:
    """Wraps a v2 trace/span/generation object to expose the v3+ ``update()`` API."""

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def update(self, **kwargs: Any) -> None:
        output = kwargs.get("output")
        if output is not None:
            self._obj.update(output=output)

    def __enter__(self) -> "_V2ObservationWrapper":
        return self

    def __exit__(self, *args: Any) -> None:
        self._obj.end()


# ---------------------------------------------------------------------------
# Context-var for tracking v2 nesting
# ---------------------------------------------------------------------------
_V2_CONTEXT_VAR: _cv.ContextVar[Any] = _cv.ContextVar("_langfuse_v2_parent")


# ---------------------------------------------------------------------------
# V2 Langfuse client wrapper
# ---------------------------------------------------------------------------
class _V2LangfuseWrapper:
    """Adapts a v2 ``Langfuse`` instance to the v3+ ``start_as_current_observation`` API."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        as_type: str,
        name: str,
        input: dict | None = None,
        metadata: dict | None = None,
        model: str | None = None,
        **_kwargs: Any,
    ):
        parent = _V2_CONTEXT_VAR.get(None)

        if parent is None:
            # Root -> trace
            trace_kwargs: dict[str, Any] = {"name": name}
            if input is not None:
                trace_kwargs["input"] = input
            if metadata is not None:
                trace_kwargs["metadata"] = metadata
            trace = self._client.trace(**trace_kwargs)
            wrapper = _V2ObservationWrapper(trace)
            token = _V2_CONTEXT_VAR.set(trace)
            try:
                yield wrapper
            finally:
                _V2_CONTEXT_VAR.reset(token)
        else:
            # Child -> span or generation
            child_kwargs: dict[str, Any] = {"name": name}
            if input is not None:
                child_kwargs["input"] = input
            if metadata is not None:
                child_kwargs["metadata"] = metadata

            if as_type == "generation":
                if model is not None:
                    child_kwargs["model"] = model
                child = parent.generation(**child_kwargs)
            else:
                child = parent.span(**child_kwargs)

            yield _V2ObservationWrapper(child)

    def flush(self) -> None:
        self._client.flush()


# ---------------------------------------------------------------------------
# V3+ Langfuse client wrapper (handles both early and later v3, plus v4)
# ---------------------------------------------------------------------------
class _V3PlusLangfuseWrapper:
    """Adapts v3+/v4+ native client to the unified ``start_as_current_observation`` API.

    For langfuse >= 3.1 (and all v4), the native ``start_as_current_observation`` method
    is available. For langfuse 3.0.x, we fall back to ``start_as_current_span`` /
    ``start_as_current_generation`` which are the separate methods provided by the
    early v3 SDK.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        # Probe once whether the unified API is available
        self._has_unified_api = hasattr(client, "start_as_current_observation")

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):
        if self._has_unified_api:
            # v3.1+ / v4+: native unified API
            with self._client.start_as_current_observation(**kwargs) as obs:
                yield obs
        else:
            # v3.0.x fallback: route to separate span/generation methods
            as_type = kwargs.pop("as_type", "span")
            method = (
                self._client.start_as_current_generation
                if as_type == "generation"
                else self._client.start_as_current_span
            )
            with method(**kwargs) as obs:
                yield obs

    def flush(self) -> None:
        self._client.flush()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_langfuse():
    """Return a version-adapted langfuse client.

    Usage::

        langfuse = get_langfuse()
        with langfuse.start_as_current_observation(
            as_type="agent", name="my-workflow", input={...}
        ) as root:
            ...
        langfuse.flush()
    """
    if IS_V2:
        from langfuse import Langfuse

        client = Langfuse()
        return _V2LangfuseWrapper(client)
    else:
        from langfuse import get_client

        client = get_client()
        return _V3PlusLangfuseWrapper(client)


def get_openai_client(api_key: str, base_url: str):
    """Return a langfuse-instrumented OpenAI client (works across v2~v4)."""
    from langfuse.openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url)


def reinit_langfuse(public_key: str, secret_key: str, host: str) -> None:
    """Re-initialize the langfuse client with new credentials (for config hot-reload)."""
    from langfuse import Langfuse

    Langfuse(public_key=public_key, secret_key=secret_key, host=host)
