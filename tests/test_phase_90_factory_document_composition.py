from __future__ import annotations

import anyio

from saxophone.app.factory import AppOverrides, _compose_document_services
from saxophone.app.settings import AppSettings


def _settings(tmp_path) -> AppSettings:
    return AppSettings.from_environment(
        {
            "SAXO_REMOTE_GPU_BASE_URL": "https://gpu.example.test",
            "SAXO_REMOTE_GPU_BEARER_TOKEN": "test-token",
            "SAXO_DATA_ROOT": str(tmp_path),
        }
    )


def test_document_composition_preserves_explicit_workflow_dependencies(tmp_path) -> None:
    artifact_repository = object()
    image_gate = object()
    extractor = object()
    process_document = object()
    process_and_persist_document = object()

    composition = _compose_document_services(
        _settings(tmp_path),
        AppOverrides(
            artifact_repository=artifact_repository,
            image_artifact_gate=image_gate,
            pdf_extractor=extractor,
            process_document=process_document,
            process_and_persist_document=process_and_persist_document,
        ),
        direct_provider=True,
        model_client=object(),
        io_limiter=anyio.CapacityLimiter(1),
    )

    assert composition.artifact_repository is artifact_repository
    assert composition.image_artifact_gate is image_gate
    assert composition.pdf_extractor is extractor
    assert composition.process_document is process_document
    assert composition.process_and_persist_document is process_and_persist_document
