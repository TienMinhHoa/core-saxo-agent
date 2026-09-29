"""Provider-independent chat contracts and application service."""

from .models import ChatResult, ChatStatus, GeneratedAnswer
from .ports import AnswerGenerator, ImageArtifactGate
from .service import AnswerQuestion

_COMPATIBILITY_EXPORTS = frozenset({"GroundedAnswerService"})


def __getattr__(name: str) -> object:
    """Load legacy chat adapters only when a compatibility caller requests one."""

    if name not in _COMPATIBILITY_EXPORTS:
        raise AttributeError(name)
    from .compatibility import GroundedAnswerService

    return GroundedAnswerService

__all__ = [
    "AnswerGenerator",
    "AnswerQuestion",
    "GroundedAnswerService",
    "ChatResult",
    "ChatStatus",
    "GeneratedAnswer",
    "ImageArtifactGate",
]
