from __future__ import annotations

from pathlib import Path

import pytest

from saxophone.app.factory import AppOverrides, create_app
from saxophone.app.settings import AppSettings, SettingsValidationError
from saxophone.ingestion.transaction import SqliteIngestionTransactionRepository
from saxophone.ingestion.concept_embedding import (
    ConceptCatalogVectorPreparationService,
)
from saxophone.ingestion.concept_repository import SqliteConceptCatalogRepository
from saxophone.ingestion.use_cases import DocumentChunkTaggingService
from saxophone.tagging.adapters import RemoteChunkTagger


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
}


class FakeRemoteGpuGateway:
    async def health(self):
        raise AssertionError("composition test must not probe the provider")


class FakeModelClient:
    async def invoke(self, request):
        raise AssertionError("composition test must not invoke the model")


def _settings(tmp_path: Path, *, enabled: str | None = None) -> AppSettings:
    environment = {
        **VALID_ENVIRONMENT,
        "SAXO_DATA_ROOT": str(tmp_path),
    }
    if enabled is not None:
        environment["SAXO_CHUNK_TAGGING_ENABLED"] = enabled
    return AppSettings.from_environment(environment)


def _app(settings: AppSettings):
    return create_app(
        settings,
        overrides=AppOverrides(
            remote_gpu_gateway=FakeRemoteGpuGateway(),
            model_client=FakeModelClient(),
            vector_index=object(),
        ),
    )


def test_chunk_tagging_feature_flag_defaults_to_disabled_and_parses_explicit_values(
    tmp_path: Path,
) -> None:
    assert _settings(tmp_path).chunk_tagging_enabled is False
    assert _settings(tmp_path, enabled="true").chunk_tagging_enabled is True
    assert _settings(tmp_path, enabled="FALSE").chunk_tagging_enabled is False


def test_chunk_tagging_feature_flag_rejects_non_boolean_values(tmp_path: Path) -> None:
    with pytest.raises(SettingsValidationError, match="SAXO_CHUNK_TAGGING_ENABLED"):
        _settings(tmp_path, enabled="on")


def test_enabled_composition_selects_chunk_tagging_and_atomic_sqlite_boundary(
    tmp_path: Path,
) -> None:
    container = _app(_settings(tmp_path, enabled="true")).state.container

    assert isinstance(container.chunk_tagger, RemoteChunkTagger)
    assert isinstance(container.chunk_tagging, DocumentChunkTaggingService)
    assert isinstance(
        container.ingestion_transaction_repository,
        SqliteIngestionTransactionRepository,
    )
    assert (
        container.ingestion_transaction_repository._path
        == (tmp_path / "ingestion.sqlite3").absolute()
    )
    assert container.ingest_extracted_document is not None
    ingest_document = container.ingest_extracted_document._ingest_document
    assert ingest_document is not None
    assert ingest_document._chunk_tagging is container.chunk_tagging
    assert ingest_document._tag_and_persist is None
    assert isinstance(
        ingest_document._concept_vector_preparation,
        ConceptCatalogVectorPreparationService,
    )
    assert isinstance(
        ingest_document._concept_catalog_repository,
        SqliteConceptCatalogRepository,
    )
    assert container.concept_catalog_repository is ingest_document._concept_catalog_repository


def test_disabled_composition_preserves_legacy_paragraph_tagging(tmp_path: Path) -> None:
    container = _app(_settings(tmp_path)).state.container

    assert container.chunk_tagger is None
    assert container.chunk_tagging is None
    assert container.ingestion_transaction_repository is None
    assert container.ingest_extracted_document is not None
    ingest_document = container.ingest_extracted_document._ingest_document
    assert ingest_document is not None
    assert ingest_document._chunk_tagging is None
    assert ingest_document._tag_and_persist is not None
    assert ingest_document._concept_vector_preparation is None
    assert ingest_document._concept_catalog_repository is None
    assert container.concept_catalog_repository is None
