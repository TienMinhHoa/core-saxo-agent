"""Shared limits for blocking I/O executed from async application code."""

from __future__ import annotations

import anyio


DEFAULT_BLOCKING_IO_CONCURRENCY = 8


def create_blocking_io_limiter(
    max_concurrency: int = DEFAULT_BLOCKING_IO_CONCURRENCY,
) -> anyio.CapacityLimiter:
    """Create the limiter used by adapters around blocking SDK calls."""

    if not isinstance(max_concurrency, int) or isinstance(max_concurrency, bool):
        raise ValueError("max_concurrency must be an integer")
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be positive")
    return anyio.CapacityLimiter(max_concurrency)
