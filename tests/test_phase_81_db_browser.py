from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saxophone.ingestion.adapters import ChromaVectorIndex
from saxophone.ingestion.ports import VectorCollectionSummary, VectorRecord, VectorRecordPage
from saxophone.interfaces.db_browser import build_database_browser_router


@dataclass
class _Browser:
    collections: tuple[VectorCollectionSummary, ...]
    page: VectorRecordPage

    async def list_collections(self):
        return self.collections

    async def get_records(self, collection_name, *, offset, limit, query, document_ref):
        assert collection_name == "saxophone_chunks"
        assert offset == 0
        assert limit == 25
        assert query == "harmony"
        assert document_ref == "music-theory-full"
        return self.page


def _router_app(browser: object | None) -> FastAPI:
    app = FastAPI()
    app.include_router(build_database_browser_router(browser=browser))
    return app


def test_db_page_serves_ui_and_assets() -> None:
    client = TestClient(_router_app(None))

    page = client.get("/db")
    stylesheet = client.get("/db/assets/db.css")
    script = client.get("/db/assets/db.js")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert 'href="/db/assets/db.css"' in page.text
    assert 'src="/db/assets/db.js"' in page.text
    assert 'id="collection-select"' in page.text
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert 'fetch("/db/api/collections"' in script.text


def test_db_collections_and_records_are_read_only_json_boundaries() -> None:
    page = VectorRecordPage(
        collection_name="saxophone_chunks",
        offset=0,
        limit=25,
        total_count=315,
        records=(
            VectorRecord(
                record_id="chunk-1",
                document="Harmony organizes vertical sonorities.",
                metadata={"document_ref": "music-theory-full", "tags": ["harmony"]},
            ),
        ),
        has_more=True,
    )
    browser = _Browser(
        collections=(
            VectorCollectionSummary(name="saxophone_chunks", count=315),
            VectorCollectionSummary(name="concept_catalog", count=24),
        ),
        page=page,
    )

    client = TestClient(_router_app(browser))
    collections = client.get("/db/api/collections")
    records = client.get(
        "/db/api/collections/saxophone_chunks/records",
        params={"q": "harmony", "document_ref": "music-theory-full", "limit": 25},
    )

    assert collections.status_code == 200
    assert collections.json() == {
        "collections": [
            {"name": "saxophone_chunks", "count": 315},
            {"name": "concept_catalog", "count": 24},
        ]
    }
    assert records.status_code == 200
    assert records.json() == {
        "collection": "saxophone_chunks",
        "offset": 0,
        "limit": 25,
        "total_count": 315,
        "has_more": True,
        "records": [
            {
                "id": "chunk-1",
                "document": "Harmony organizes vertical sonorities.",
                "metadata": {"document_ref": "music-theory-full", "tags": ["harmony"]},
            }
        ],
    }


def test_db_browser_reports_unconfigured_capability_and_rejects_bad_paging() -> None:
    client = TestClient(_router_app(None))

    assert client.get("/db/api/collections").status_code == 503
    response = client.get(
        "/db/api/collections/saxophone_chunks/records",
        params={"limit": 0},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_chroma_browser_lists_and_reads_configured_collections() -> None:
    class _Collection:
        def __init__(self, name: str, rows: list[dict[str, object]]) -> None:
            self.name = name
            self._rows = rows
            self.get_calls: list[dict[str, object]] = []

        def count(self) -> int:
            return len(self._rows)

        def get(self, **kwargs):
            self.get_calls.append(kwargs)
            if kwargs.get("include") == []:
                return {"ids": [row["id"] for row in self._rows]}
            rows = self._rows[kwargs.get("offset", 0) : kwargs.get("offset", 0) + kwargs["limit"]]
            return {
                "ids": [row["id"] for row in rows],
                "documents": [row["document"] for row in rows],
                "metadatas": [row["metadata"] for row in rows],
            }

    chunks = _Collection(
        "saxophone_chunks",
        [
            {
                "id": "chunk-1",
                "document": "Harmony text",
                "metadata": {"document_ref": "music-theory-full"},
            }
        ],
    )
    concepts = _Collection("concept_catalog", [])
    index = ChromaVectorIndex(chunks, concept_collection=concepts)

    assert await index.list_collections() == (
        VectorCollectionSummary("saxophone_chunks", 1),
        VectorCollectionSummary("concept_catalog", 0),
    )
    page = await index.get_records(
        "saxophone_chunks",
        offset=0,
        limit=10,
        query="harmony",
        document_ref="music-theory-full",
    )

    assert page.total_count == 1
    assert page.records[0].record_id == "chunk-1"
    assert chunks.get_calls == [
        {
            "where": {"document_ref": "music-theory-full"},
            "where_document": {"$contains": "harmony"},
            "include": [],
        },
        {
        "limit": 10,
        "offset": 0,
        "where": {"document_ref": "music-theory-full"},
        "where_document": {"$contains": "harmony"},
        "include": ["documents", "metadatas"],
        },
    ]


@pytest.mark.anyio
async def test_chroma_browser_rejects_unknown_collection() -> None:
    class _Collection:
        name = "saxophone_chunks"

        def count(self):
            return 0

    index = ChromaVectorIndex(_Collection(), concept_collection=_Collection())

    with pytest.raises(ValueError, match="collection"):
        await index.get_records(
            "unknown",
            offset=0,
            limit=10,
            query=None,
            document_ref=None,
        )


@pytest.mark.anyio
async def test_chroma_browser_reads_real_chroma_without_embeddings() -> None:
    import chromadb

    client = chromadb.Client()
    suffix = uuid4().hex
    chunks = client.get_or_create_collection(f"db_browser_chunks_{suffix}")
    concepts = client.get_or_create_collection(f"db_browser_concepts_{suffix}")
    chunks.upsert(
        ids=["chunk-1"],
        embeddings=[[0.1, 0.2]],
        documents=["Harmony text"],
        metadatas=[{"document_ref": "music-theory-full"}],
    )
    index = ChromaVectorIndex(chunks, concept_collection=concepts)

    page = await index.get_records(
        chunks.name,
        offset=0,
        limit=25,
        query="Harmony",
        document_ref="music-theory-full",
    )

    assert page.total_count == 1
    assert page.records == (
        VectorRecord(
            record_id="chunk-1",
            document="Harmony text",
            metadata={"document_ref": "music-theory-full"},
        ),
    )
