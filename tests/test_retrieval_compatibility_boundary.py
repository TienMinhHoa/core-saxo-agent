from __future__ import annotations

import importlib
import subprocess
import sys

import saxophone.agent as agent_package
import saxophone.agent.evidence_selection as active_selection
import saxophone.retrieval.selector_compatibility as selector_compatibility


_COMPATIBILITY_EXPORTS = (
    "QuestionRequest",
    "QuestionRetrievalService",
    "RetrievalBundle",
    "RetrievalBundleStatus",
)


def test_retrieval_package_keeps_compatibility_exports_lazy() -> None:
    """Do not load the legacy question flow while importing active retrieval APIs."""

    package = importlib.import_module("saxophone.retrieval")
    for name in _COMPATIBILITY_EXPORTS:
        package.__dict__.pop(name, None)
    importlib.reload(package)

    assert all(name not in package.__dict__ for name in _COMPATIBILITY_EXPORTS)

    request_type = package.QuestionRequest

    assert request_type.__module__ == "saxophone.retrieval.question_retrieval"
    assert all(name not in package.__dict__ for name in _COMPATIBILITY_EXPORTS)


def test_retrieval_package_preserves_explicit_compatibility_imports() -> None:
    """Existing callers can still import each compatibility symbol explicitly."""

    from saxophone.retrieval import (
        QuestionRequest,
        QuestionRetrievalService,
        RetrievalBundle,
        RetrievalBundleStatus,
    )

    assert QuestionRequest.__name__ == "QuestionRequest"
    assert QuestionRetrievalService.__name__ == "QuestionRetrievalService"
    assert RetrievalBundle.__name__ == "RetrievalBundle"
    assert RetrievalBundleStatus.__name__ == "RetrievalBundleStatus"


def test_retrieval_selector_exports_load_only_when_requested() -> None:
    """Keep optional selector modules out of basic retrieval imports."""

    script = """
import importlib
import sys

package = importlib.import_module("saxophone.retrieval")
optional_modules = (
    "saxophone.retrieval.role_selection",
    "saxophone.retrieval.renderers",
    "saxophone.retrieval.paragraph_traversal",
    "saxophone.retrieval.paragraph_selection",
    "saxophone.retrieval.context_limiter",
)
assert all(name not in sys.modules for name in optional_modules)

assert package.StructuredParagraphSelector.__module__ == "saxophone.retrieval.paragraph_selection"
assert package.ConceptRoleSelector.__module__ == "saxophone.retrieval.role_selection"
assert "saxophone.retrieval.paragraph_selection" in sys.modules
assert "saxophone.retrieval.role_selection" in sys.modules
assert "saxophone.retrieval.paragraph_traversal" not in sys.modules
assert "saxophone.retrieval.context_limiter" not in sys.modules

assert package.ContextLimiter.__module__ == "saxophone.retrieval.context_limiter"
assert "saxophone.retrieval.context_limiter" in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_factory_import_does_not_load_legacy_question_retrieval() -> None:
    """Keep composition-root imports free of the compatibility retrieval graph."""

    script = """
import importlib
import sys

importlib.import_module("saxophone.app.factory")
assert "saxophone.retrieval.question_retrieval" not in sys.modules
assert "saxophone.chat.compatibility" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_agent_import_does_not_load_legacy_selector_implementations() -> None:
    """Keep provider-specific selector modules behind the selection boundary."""

    script = """
import importlib
import sys

importlib.import_module("saxophone.agent")
optional_modules = (
    "saxophone.retrieval.paragraph_selection",
    "saxophone.retrieval.paragraph_traversal",
    "saxophone.retrieval.role_selection",
)
assert all(name not in sys.modules for name in optional_modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_legacy_selector_adapter_is_lazy_outside_the_active_selection_module() -> None:
    """Keep the migration-only selector branch behind a compatibility module."""

    assert "adapt_legacy_selector" not in active_selection.__dict__
    assert "adapt_legacy_selector" not in agent_package.__dict__
    assert callable(selector_compatibility.adapt_legacy_selector)


def test_legacy_selector_adapter_imports_remain_compatible() -> None:
    """Preserve explicit imports while resolving the adapter lazily."""

    from saxophone.agent import adapt_legacy_selector as package_adapter
    from saxophone.agent.evidence_selection import adapt_legacy_selector as module_adapter

    assert package_adapter is selector_compatibility.adapt_legacy_selector
    assert module_adapter is selector_compatibility.adapt_legacy_selector


def test_question_retrieval_uses_the_compatibility_selector_boundary(monkeypatch) -> None:
    """Do not make the legacy retrieval service reach into active selection internals."""

    from saxophone.retrieval.question_retrieval import QuestionRetrievalService

    sentinel = object()
    seen: list[object] = []

    def fake_adapter(selector: object) -> object:
        seen.append(selector)
        return sentinel

    monkeypatch.setattr(selector_compatibility, "adapt_legacy_selector", fake_adapter)

    service = QuestionRetrievalService(retriever=object(), selector="legacy")

    assert seen == ["legacy"]
    assert service._selector is sentinel
