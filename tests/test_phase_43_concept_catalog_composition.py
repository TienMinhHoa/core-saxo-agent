from __future__ import annotations

import sys

import pytest

from saxophone.app.settings import AppSettings, SettingsValidationError
from saxophone.platform.chroma import create_chroma_vector_index


VALID_ENVIRONMENT = {
    "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
    "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
}


def test_settings_configure_a_distinct_concept_catalog_collection() -> None:
    default_settings = AppSettings.from_environment(VALID_ENVIRONMENT)
    settings = AppSettings.from_environment(
        {
            **VALID_ENVIRONMENT,
            "SAXO_CHROMA_CONCEPT_COLLECTION_NAME": "concept_catalog_v2",
        }
    )

    assert default_settings.chroma_concept_collection_name == "concept_catalog"
    assert settings.chroma_concept_collection_name == "concept_catalog_v2"


@pytest.mark.parametrize("value", ["", "bad name", "a", "concept/catalog"])
def test_settings_reject_invalid_concept_catalog_collection_name(value: str) -> None:
    with pytest.raises(
        SettingsValidationError,
        match="SAXO_CHROMA_CONCEPT_COLLECTION_NAME",
    ):
        AppSettings.from_environment(
            {
                **VALID_ENVIRONMENT,
                "SAXO_CHROMA_CONCEPT_COLLECTION_NAME": value,
            }
        )


def test_chroma_factory_creates_separate_chunk_and_concept_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    captured: dict[str, object] = {}

    class FakeCollection:
        def __init__(self, metadata: dict[str, object]) -> None:
            self.metadata = metadata

    class FakeClient:
        def __init__(self, *, path: str) -> None:
            self.path = path

        def get_or_create_collection(
            self,
            *,
            name: str,
            metadata: dict[str, object],
        ) -> FakeCollection:
            calls.append((name, metadata))
            return FakeCollection(metadata)

        def close(self) -> None:
            pass

    class FakeChroma:
        PersistentClient = FakeClient

    class CapturingVectorIndex:
        def __init__(self, chunk_collection, *, concept_collection, **kwargs) -> None:
            captured["chunk_collection"] = chunk_collection
            captured["concept_collection"] = concept_collection
            captured["kwargs"] = kwargs

    monkeypatch.setitem(sys.modules, "chromadb", FakeChroma)
    monkeypatch.setattr(
        "saxophone.platform.chroma.ChromaVectorIndex",
        CapturingVectorIndex,
    )

    settings = AppSettings.from_environment(
        {
            **VALID_ENVIRONMENT,
            "SAXO_CHROMA_COLLECTION_NAME": "document_chunks",
            "SAXO_CHROMA_CONCEPT_COLLECTION_NAME": "concept_catalog",
            "SAXO_EMBEDDING_DIMENSION": "4",
        }
    )

    create_chroma_vector_index(settings)

    assert [name for name, _ in calls] == [
        "document_chunks",
        "concept_catalog",
    ]
    assert captured["chunk_collection"] is not captured["concept_collection"]
    captured_kwargs = captured["kwargs"]
    assert isinstance(captured_kwargs, dict)
    assert captured_kwargs["embedding_dimension"] == 4
