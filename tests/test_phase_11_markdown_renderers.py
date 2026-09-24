from saxophone.retrieval.renderers import (
    AnswerContextMarkdownRenderer,
    AnswerContextModel,
    ConceptInventory,
    ConceptInventoryItem,
    ParentChunk,
    RoleAvailability,
    RoleSelectionMarkdownRenderer,
    SourceParagraph,
    SelectedConceptRole,
)


def _inventory() -> ConceptInventory:
    return ConceptInventory(
        (
            ConceptInventoryItem(
                "Major triad",
                (RoleAvailability("Definition", 3), RoleAvailability("Procedure", 2)),
                (ParentChunk("chunk-01", 1), ParentChunk("chunk-02", 2)),
            ),
        )
    )


def test_role_selection_renderer_is_deterministic_and_keeps_unicode() -> None:
    rendered = RoleSelectionMarkdownRenderer().render_role_selection(
        "Khái niệm là gì?", _inventory()
    )
    assert rendered == (
        "# Concept and Role Selection\n\n"
        "## User question\n\n"
        "Khái niệm là gì?\n\n"
        "## Candidate concepts from retrieved chunks\n\n"
        "### Concept: Major triad\n\n"
        "- Available role: Definition — 3 paragraphs\n"
        "- Available role: Procedure — 2 paragraphs\n"
        "- Parent chunks: chunk-01 (rank 1), chunk-02 (rank 2)\n"
    )


def test_answer_context_renders_each_source_once_and_rejects_dangling_refs() -> None:
    context = AnswerContextModel(
        selected_roles=(
            SelectedConceptRole("Major triad", "Definition", ("paragraph-A",), (ParentChunk("chunk-01", 1),)),
        ),
        paragraphs=(
            SourceParagraph(
                "paragraph-A", "music.md", "Major triads", (), "A major triad — root, third, fifth.", ("Major triad — Definition",), (), (),
            ),
        ),
    )
    rendered = AnswerContextMarkdownRenderer().render_answer_context("What is it?", context)
    assert rendered.count("A major triad — root, third, fifth.") == 1
    assert "## Concept-role map" in rendered
    assert "### [1]" in rendered
    assert "paragraph-A" not in rendered
