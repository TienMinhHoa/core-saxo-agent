import time

import anyio
import pytest

from saxophone.ingestion.adapters import ChromaVectorIndex
from saxophone.platform.concurrency import create_blocking_io_limiter


def test_blocking_io_limiter_rejects_invalid_capacity() -> None:
    with pytest.raises(ValueError, match="positive"):
        create_blocking_io_limiter(0)

    with pytest.raises(ValueError, match="integer"):
        create_blocking_io_limiter(True)


def test_blocking_io_limiter_has_configured_capacity() -> None:
    limiter = create_blocking_io_limiter(3)

    assert limiter.total_tokens == 3


def test_chroma_blocking_query_does_not_starve_event_loop() -> None:
    class SlowCollection:
        def query(self, **_: object) -> dict[str, list[list[object]]]:
            time.sleep(0.08)
            return {
                "ids": [["chunk-1"]],
                "documents": [["slow result"]],
                "metadatas": [[{"chunk_id": "chunk-1", "document_ref": "doc-1"}]],
                "distances": [[0.0]],
            }

    index = ChromaVectorIndex(
        SlowCollection(),
        io_limiter=create_blocking_io_limiter(1),
    )
    observed_ticks = 0
    query_finished = anyio.Event()

    async def run_query() -> None:
        await index.search((1.0, 0.0, 0.0), limit=1)
        query_finished.set()

    async def observe_event_loop() -> None:
        nonlocal observed_ticks
        while not query_finished.is_set():
            await anyio.sleep(0.005)
            observed_ticks += 1

    async def exercise() -> None:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_query)
            task_group.start_soon(observe_event_loop)

    anyio.run(exercise)

    assert observed_ticks >= 3
