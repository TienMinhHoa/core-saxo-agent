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


def test_select_chroma_records_extracts_only_mapping_records() -> None:
    from music_rag.ui_workflows import select_chroma_records

    response = {
        "items": [
            {"record": {"chunk_id": "first"}},
            {"record": ["not a record"]},
            None,
            {"record": {"chunk_id": "second"}},
        ]
    }

    assert select_chroma_records(response) == [
        {"chunk_id": "first"},
        {"chunk_id": "second"},
    ]


def test_select_chroma_records_returns_empty_for_invalid_response_or_items() -> None:
    from music_rag.ui_workflows import select_chroma_records

    assert select_chroma_records(None) == []
    assert select_chroma_records({"items": "not a list"}) == []


def test_select_chroma_records_preserves_duplicate_records_for_rendering() -> None:
    from music_rag.ui_workflows import select_chroma_records

    record = {"chunk_id": "same"}

    assert select_chroma_records({"items": [{"record": record}, {"record": record}]}) == [record, record]


def test_handle_chroma_request_rejects_blank_input_before_service_access() -> None:
    from music_rag.ui_workflows import handle_chroma_request

    class ExplodingService:
        def understand_request(self, request: str) -> object:
            raise AssertionError("blank requests must not reach the service")

    assert handle_chroma_request(
        "  ",
        chroma_service=ExplodingService(),
        access_scope="public",
        render_results=lambda records: ("unused", []),
    ) == ("Nh蘯ｭp cﾃ｢u h盻淑 ﾄ黛ｻ・tﾃｬm trong header chunks.", "", [])


def test_handle_answer_request_rejects_blank_input_before_service_access() -> None:
    from music_rag.ui_workflows import handle_answer_request

    class ExplodingService:
        def understand_request(self, request: str) -> object:
            raise AssertionError("blank requests must not reach the service")

    assert handle_answer_request(
        "  ",
        chroma_service=ExplodingService(),
        access_scope="public",
        render_results=lambda records: ("unused", []),
        format_cost=lambda result: "unused",
    ) == ("Nh蘯ｭp cﾃ｢u h盻淑 ﾄ黛ｻ・t盻貧g h盻｣p cﾃ｢u tr蘯｣ l盻拱.", "", "", [], "")
