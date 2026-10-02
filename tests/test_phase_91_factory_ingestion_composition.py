from __future__ import annotations

import anyio

from saxophone.app.factory import AppOverrides, _compose_ingestion_services
from saxophone.app.settings import AppSettings


def _settings(tmp_path) -> AppSettings:
    return AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
            "SAXO_DATA_ROOT": str(tmp_path),
        }
    )


def test_ingestion_composition_preserves_explicit_dependencies(tmp_path) -> None:
    embedding_provider = object()
    embedding_reuse = object()
    content_ledger = object()
    vector_index = object()
    index_document = object()
    tagged_paragraph_repository = object()
    tag_catalog_repository = object()
    tag_generator = object()
    tag_conflict_resolver = object()
    document_ingestion = object()
    ingest_extracted_document = object()
    artifact_repository = object()

    composition = _compose_ingestion_services(
        _settings(tmp_path),
        AppOverrides(
            embedding_provider=embedding_provider,
            embedding_reuse=embedding_reuse,
            content_ledger=content_ledger,
            vector_index=vector_index,
            index_document=index_document,
            tagged_paragraph_repository=tagged_paragraph_repository,
            tag_catalog_repository=tag_catalog_repository,
            tag_generator=tag_generator,
            tag_conflict_resolver=tag_conflict_resolver,
            document_ingestion=document_ingestion,
            ingest_extracted_document=ingest_extracted_document,
        ),
        model_client=object(),
        structured_llm_provider=object(),
        event_sink=object(),
        artifact_repository=artifact_repository,
        io_limiter=anyio.CapacityLimiter(1),
    )

    assert composition.embedding_provider is embedding_provider
    assert composition.embedding_reuse is embedding_reuse
    assert composition.content_ledger is content_ledger
    assert composition.vector_index is vector_index
    assert composition.index_document is index_document
    assert composition.tagged_paragraph_repository is tagged_paragraph_repository
    assert composition.tag_catalog_repository is tag_catalog_repository
    assert composition.tag_generator is tag_generator
    assert composition.tag_conflict_resolver is tag_conflict_resolver
    assert composition.document_ingestion is document_ingestion
    assert composition.ingest_extracted_document is ingest_extracted_document
    assert composition.ingestion_database == tmp_path / "ingestion.sqlite3"
