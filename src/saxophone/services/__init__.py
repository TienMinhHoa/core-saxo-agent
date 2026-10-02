"""Internal application service facade with lazy use-case resolution."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .extract_topic import ExtractTopicService


__all__ = ["ExtractTopicService"]


def __getattr__(name: str) -> Any:
    """Load service implementations only when a caller requests one."""

    if name != "ExtractTopicService":
        raise AttributeError(name)
    value = getattr(import_module(".extract_topic", __name__), name)
    globals()[name] = value
    return value
