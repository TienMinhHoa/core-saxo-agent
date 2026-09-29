from __future__ import annotations

import importlib


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
