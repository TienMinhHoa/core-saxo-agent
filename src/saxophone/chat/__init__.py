"""Provider-independent chat facade with lazy application implementations."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import ChatResult, ChatStatus, GeneratedAnswer
    from .ports import AnswerGenerator, ImageArtifactGate
    from .service import AnswerQuestion


_EXPORTS = {
    "ChatResult": (".models", "ChatResult"),
    "ChatStatus": (".models", "ChatStatus"),
    "GeneratedAnswer": (".models", "GeneratedAnswer"),
    "AnswerGenerator": (".ports", "AnswerGenerator"),
    "ImageArtifactGate": (".ports", "ImageArtifactGate"),
    "AnswerQuestion": (".service", "AnswerQuestion"),
}

_COMPATIBILITY_EXPORTS = frozenset({"GroundedAnswerService"})


def __getattr__(name: str) -> Any:
    """Resolve active contracts and legacy adapters only when requested."""

    if name in _COMPATIBILITY_EXPORTS:
        from .compatibility import GroundedAnswerService

        return GroundedAnswerService
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "AnswerGenerator",
    "AnswerQuestion",
    "ChatResult",
    "ChatStatus",
    "GeneratedAnswer",
    "ImageArtifactGate",
]
