from __future__ import annotations

import gc
from pathlib import Path

import anyio

from saxophone.app.settings import AppSettings
from saxophone.ingestion.models import ChunkIndexRecord
from saxophone.platform.chroma import create_chroma_vector_index


def test_real_persistent_chroma_round_trip(tmp_path: Path) -> None:
    settings = AppSettings(
        data_root=tmp_path / "data",
        remote_gpu_base_url="https://gpu.example.test",
        remote_gpu_bearer_token="test-token",
        chroma_persist_directory=tmp_path / "chroma",
        chroma_collection_name="live_contract",
        embedding_dimension=3,
    )

    index = create_chroma_vector_index(settings)
    record = ChunkIndexRecord(
        chunk_id="chunk-live-1",
        document_ref="document-live-1",
        source_version="v1",
        search_text="persistent Chroma contract",
        embedding=(1.0, 0.0, 0.0),
        embedding_profile="test-embedding",
        access_scope="public",
        metadata={"page": 1},
    )

    async def exercise() -> None:
        await index.upsert_chunks((record,))
        assert await index.list_chunk_ids(document_ref=record.document_ref) == (record.chunk_id,)
        hits = await index.search(record.embedding, filters={"document_ref": record.document_ref})
        assert [hit.chunk_id for hit in hits] == [record.chunk_id]
        assert hits[0].document == record.search_text
        assert hits[0].metadata == {
            "page": 1,
            "document_ref": record.document_ref,
            "source_version": record.source_version,
            "embedding_profile": record.embedding_profile,
            "access_scope": record.access_scope,
        }
        await index.delete_chunks((record.chunk_id,))
        assert await index.list_chunk_ids(document_ref=record.document_ref) == ()

    try:
        anyio.run(exercise)
    finally:
        # Chroma 1.5.x keeps SQLite handles behind the client/collection graph.
        # Release that graph before pytest removes tmp_path on Windows.
        del index
        gc.collect()
