import pytest

from saxophone.retrieval.paragraph_traversal import ParagraphTraversal
from saxophone.retrieval.renderers import ParentChunk, SelectedConceptRole, SourceParagraph
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


def _paragraph(ref: str, chunk: str) -> SourceParagraph:
    return SourceParagraph(ref, "book.md", chunk, (), ref + " text", (), (), ())


def test_traversal_resolves_roles_within_candidate_chunks_and_deduplicates_paragraphs() -> None:
    selections = (
        SelectedConceptRole("Major triad", "Definition", (), (ParentChunk("chunk-01", 1),)),
        SelectedConceptRole("Chord construction", "Procedure", (), (ParentChunk("chunk-02", 2),)),
    )
    relations = (
        ParagraphConceptRole("p-1", "Major triad", ContentRole.DEFINITION),
        ParagraphConceptRole("p-2", "Chord construction", ContentRole.PROCEDURE),
        ParagraphConceptRole("p-2", "Major triad", ContentRole.PROCEDURE),
        ParagraphConceptRole("p-outside", "Major triad", ContentRole.DEFINITION),
    )
    result = ParagraphTraversal().resolve(
        selections,
        relations,
        {
            "p-1": _paragraph("p-1", "chunk-01"),
            "p-2": _paragraph("p-2", "chunk-02"),
            "p-outside": _paragraph("p-outside", "chunk-99"),
        },
    )

    assert result.selected_roles[0].paragraph_refs == ("p-1",)
    assert result.selected_roles[1].paragraph_refs == ("p-2",)
    assert tuple(p.paragraph_ref for p in result.paragraphs) == ("p-1", "p-2")


def test_traversal_rejects_missing_paragraph_and_duplicate_relations() -> None:
    selection = SelectedConceptRole("Harmony", "Definition", (), (ParentChunk("chunk-01", 1),))
    relation = ParagraphConceptRole("p-1", "Harmony", ContentRole.DEFINITION)
    traversal = ParagraphTraversal()

    with pytest.raises(ValueError, match="missing paragraph"):
        traversal.resolve((selection,), (relation,), {},)

    with pytest.raises(ValueError, match="duplicate"):
        traversal.resolve((selection,), (relation, relation), {"p-1": _paragraph("p-1", "chunk-01")})
