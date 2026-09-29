from __future__ import annotations

from saxophone.chat import GroundedAnswerService as exported_service
from saxophone.chat.compatibility import GroundedAnswerService
from saxophone.chat.service import GroundedAnswerService as service_module_service


def test_grounded_answer_service_isolated_behind_compatibility_boundary() -> None:
    """Keep the legacy chat contract available while isolating its implementation."""

    assert GroundedAnswerService.__module__ == "saxophone.chat.compatibility"
    assert service_module_service is GroundedAnswerService
    assert exported_service is GroundedAnswerService
