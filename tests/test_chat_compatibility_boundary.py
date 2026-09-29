from __future__ import annotations

import importlib
from types import SimpleNamespace

import saxophone.chat as chat_package
import saxophone.chat.service as service_module
import saxophone.interfaces.api as api
from saxophone.chat import GroundedAnswerService as exported_service
from saxophone.chat.compatibility import AnswerSource, GroundedAnswerService
from saxophone.chat.service import GroundedAnswerService as service_module_service


def test_grounded_answer_service_isolated_behind_compatibility_boundary() -> None:
    """Keep the legacy chat contract available while isolating its implementation."""

    assert GroundedAnswerService.__module__ == "saxophone.chat.compatibility"
    assert service_module_service is GroundedAnswerService
    assert exported_service is GroundedAnswerService


def test_active_chat_module_resolves_legacy_service_lazily() -> None:
    """Keep the compatibility implementation out of the active module namespace."""

    service_module = importlib.import_module("saxophone.chat.service")

    assert "GroundedAnswerService" not in service_module.__dict__
    assert "QuestionRequest" not in service_module.__dict__
    assert service_module.GroundedAnswerService is GroundedAnswerService


def test_chat_package_resolves_legacy_service_lazily() -> None:
    """Keep the compatibility implementation out of the package namespace."""

    assert "GroundedAnswerService" not in chat_package.__dict__
    assert chat_package.GroundedAnswerService is GroundedAnswerService


def test_api_source_projection_bypasses_active_chat_service(monkeypatch) -> None:
    """Keep API source projection on the explicit compatibility boundary."""

    def fail_legacy_resolution(name: str) -> object:
        raise AssertionError(f"legacy export resolved through active service: {name}")

    monkeypatch.setattr(service_module, "__getattr__", fail_legacy_resolution)
    source = api._source_from_evidence(
        SimpleNamespace(paragraph="p-1", chunk="c-1", page=3),
        source_ref="document.pdf",
        image_refs=(),
    )

    assert isinstance(source, AnswerSource)
    assert source.paragraph_ref == "p-1"
