from __future__ import annotations

import importlib

from saxophone.chat import GroundedAnswerService as exported_service
from saxophone.chat.compatibility import GroundedAnswerService
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
    assert service_module.GroundedAnswerService is GroundedAnswerService
