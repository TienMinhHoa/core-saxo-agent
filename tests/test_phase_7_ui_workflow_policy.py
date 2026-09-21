"""Contract tests for pure answer-evidence selection policy."""

from __future__ import annotations


def test_select_answer_records_preserves_selected_then_adds_unique_final_hits() -> None:
    from music_rag.ui_workflows import select_answer_records

    response = {
        "items": [
            {"record": {"chunk_id": "selected", "text": "first"}},
            {"record": {"chunk_id": "duplicate", "text": "from response"}},
            {"record": {"chunk_id": "missing-id"}},
            {"record": {"chunk_id": 42}},
        ]
    }
    final_hits = [
        {"chunk_id": "duplicate", "text": "from final hits"},
        {"chunk_id": "final-1", "text": "second"},
        {"chunk_id": "final-2", "text": "third"},
        {"chunk_id": "final-3", "text": "not included"},
    ]

    assert select_answer_records(response, final_hits) == [
        {"chunk_id": "selected", "text": "first"},
        {"chunk_id": "duplicate", "text": "from response"},
        {"chunk_id": "missing-id"},
        {"chunk_id": "final-1", "text": "second"},
        {"chunk_id": "final-2", "text": "third"},
    ]


def test_select_answer_records_returns_empty_for_non_mapping_items() -> None:
    from music_rag.ui_workflows import select_answer_records

    assert select_answer_records({"items": [None, {"record": []}]}, [None, []]) == []


def test_select_answer_records_rejects_invalid_response_shape() -> None:
    from music_rag.ui_workflows import select_answer_records

    assert select_answer_records(None, [{"chunk_id": "final"}]) == []
