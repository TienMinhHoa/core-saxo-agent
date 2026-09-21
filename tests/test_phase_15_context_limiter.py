import pytest

from saxophone.retrieval.context_limiter import ContextLimiter
from saxophone.retrieval.renderers import AnswerContextModel, SelectedConceptRole, SourceParagraph


def _paragraph(ref: str, text: str) -> SourceParagraph:
    return SourceParagraph(ref, "book.md", "chunk-01", (), text, (), (), ())


def _context() -> AnswerContextModel:
    return AnswerContextModel(
        (SelectedConceptRole("Harmony", "Definition", ("p-1", "p-2"), ()),),
        (_paragraph("p-1", "one two"), _paragraph("p-2", "three four five")),
    )


def test_limiter_preserves_order_and_updates_selected_refs() -> None:
    result = ContextLimiter().limit(_context(), max_paragraphs=1, max_tokens=10)

    assert tuple(item.paragraph_ref for item in result.paragraphs) == ("p-1",)
    assert result.selected_roles[0].paragraph_refs == ("p-1",)


def test_limiter_applies_token_budget_without_splitting_paragraphs() -> None:
    result = ContextLimiter().limit(_context(), max_paragraphs=5, max_tokens=4)

    assert tuple(item.paragraph_ref for item in result.paragraphs) == ("p-1",)
    assert result.selected_roles[0].paragraph_refs == ("p-1",)


def test_limiter_rejects_invalid_limits_and_unfittable_first_paragraph() -> None:
    with pytest.raises(ValueError, match="positive"):
        ContextLimiter().limit(_context(), max_paragraphs=0, max_tokens=10)
    with pytest.raises(ValueError, match="exceeds token limit"):
        ContextLimiter().limit(_context(), max_paragraphs=5, max_tokens=1)
