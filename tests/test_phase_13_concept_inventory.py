import pytest

from saxophone.retrieval.renderers import ConceptInventoryBuilder
from saxophone.tagging.models import ContentRole, ParagraphConceptRole


def test_builder_aggregates_roles_paragraph_counts_and_parent_chunks() -> None:
    relations = (
        ParagraphConceptRole("p-2", "Major triad", ContentRole.PROCEDURE),
        ParagraphConceptRole("p-1", "Major triad", ContentRole.DEFINITION),
        ParagraphConceptRole("p-3", "Major triad", ContentRole.DEFINITION),
        ParagraphConceptRole("p-4", "Chord construction", ContentRole.EXPLANATION),
    )
    inventory = ConceptInventoryBuilder().build(
        relations,
        paragraph_chunks={"p-1": "chunk-01", "p-2": "chunk-02", "p-3": "chunk-01", "p-4": "chunk-02"},
        chunk_ranks={"chunk-01": 1, "chunk-02": 2},
    )

    assert [item.concept for item in inventory.concepts] == ["Major triad", "Chord construction"]
    assert inventory.concepts[0].available_roles[0].role == "Definition"
    assert inventory.concepts[0].available_roles[0].paragraph_count == 2
    assert inventory.concepts[0].parent_chunks[0].chunk_id == "chunk-01"
    assert inventory.concepts[0].parent_chunks[0].rank == 1


def test_builder_rejects_missing_chunk_rank_and_duplicate_relations() -> None:
    relation = ParagraphConceptRole("p-1", "Harmony", ContentRole.DEFINITION)
    builder = ConceptInventoryBuilder()

    with pytest.raises(ValueError, match="chunk rank"):
        builder.build((relation,), paragraph_chunks={"p-1": "chunk-01"}, chunk_ranks={})

    with pytest.raises(ValueError, match="duplicate"):
        builder.build(
            (relation, relation),
            paragraph_chunks={"p-1": "chunk-01"},
            chunk_ranks={"chunk-01": 1},
        )
