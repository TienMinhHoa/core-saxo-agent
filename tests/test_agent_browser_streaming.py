from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/saxophone/interfaces/api/assets/chat/chat.js"
HARNESS = ROOT / "tests/fixtures/agent_chat_browser.cjs"


def _browser(**scenario):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute browser behavior tests")
    process = subprocess.run(
        [node, str(HARNESS), str(SCRIPT)], input=json.dumps(scenario),
        text=True, capture_output=True, timeout=10, check=False,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def _frames(answer="A triad has three notes [1].", *, source=None):
    return [
        {"type": "run_started", "run_id": "run-browser"},
        {"type": "stage_started", "run_id": "run-browser", "stage": "document_search"},
        {"type": "tool_completed", "run_id": "run-browser", "tool": "document_search", "hit_count": 2},
        {"type": "run_result", "run_id": "run-browser", "result": {
            "status": "answered", "answer": answer, "sources": [source] if source else [],
            "model_version": "test-chat",
        }},
        {"type": "run_completed", "run_id": "run-browser", "status": "answered"},
    ]


@pytest.mark.parametrize("crlf,chunk_size", [(False, 17), (True, 1)])
def test_browser_consumes_fragmented_sse_and_renders_final_answer(crlf, chunk_size) -> None:
    answer = "Caf\u00e9: a triad has three notes [1]."
    result = _browser(frames=_frames(answer), crlf=crlf, chunkSize=chunk_size)

    assert result["calls"][0]["url"] == "/agent/chat/stream"
    assert result["calls"][0]["body"]["filters"] == {"document_ref": "music-book"}
    assert result["calls"][0]["body"]["max_tokens"] == 2400
    assert answer in result["text"]
    assert not result["buttonDisabled"]


def test_browser_keeps_a_visible_timeline_of_safe_thinking_events() -> None:
    frames = [
        {"type": "run_started", "run_id": "run-browser"},
        {
            "type": "thinking",
            "run_id": "run-browser",
            "text": "Đã tìm thấy 2 chunk",
        },
        {
            "type": "thinking",
            "run_id": "run-browser",
            "text": "Đang chọn paragraph liên quan",
        },
        {
            "type": "run_result",
            "run_id": "run-browser",
            "result": {
                "status": "answered",
                "answer": "Rhythm is the organization of musical time.",
                "sources": [],
                "model_version": "test-chat",
            },
        },
        {"type": "run_completed", "run_id": "run-browser", "status": "answered"},
    ]

    result = _browser(frames=frames)

    assert "Đã tìm thấy 2 chunk" in result["text"]
    assert "Đang chọn paragraph liên quan" in result["text"]


def test_browser_falls_back_to_legacy_json_only_when_stream_is_disabled() -> None:
    result = _browser(streamStatus=503, jsonResult={
        "status": "answered", "answer": "Compatibility answer.", "sources": [],
    })

    assert [call["url"] for call in result["calls"]] == [
        "/agent/chat/stream", "/agent/chat/messages",
    ]
    assert result["calls"][0]["body"] == result["calls"][1]["body"]
    assert "Compatibility answer." in result["text"]
    assert not result["buttonDisabled"]


def test_browser_does_not_duplicate_run_when_stream_request_fails() -> None:
    result = _browser(streamStatus=500)

    assert [call["url"] for call in result["calls"]] == ["/agent/chat/stream"]
    assert not result["buttonDisabled"]


def test_browser_sends_previous_turns_without_duplicating_current_question() -> None:
    answer = "Charlie Parker played alto saxophone in E-flat."
    result = _browser(
        initialQuestion="Which saxophone did Parker play?", frames=_frames(answer),
        followUps=["Which written key produces concert C major?"],
    )
    assert result["calls"][0]["body"].get("history", []) == []
    assert result["calls"][1]["body"]["history"] == [
        {"role": "user", "content": "Which saxophone did Parker play?"},
        {"role": "assistant", "content": answer},
    ]
    assert result["calls"][1]["body"]["question"] == "Which written key produces concert C major?"


def test_browser_clear_chat_clears_history_for_next_request() -> None:
    result = _browser(frames=_frames(), followUps=["New conversation"], clearBeforeFollowUp=True)
    assert result["calls"][1]["body"].get("history", []) == []


def test_browser_does_not_add_transport_error_messages_to_history() -> None:
    result = _browser(frames=_frames(), streamStatuses=[500, 200], followUps=["Try again"])
    assert result["calls"][1]["body"].get("history", []) == []


def test_browser_bounds_history_count_and_content_size() -> None:
    result = _browser(frames=_frames("a" * 5000), followUps=["q" * 5000] * 12)
    history = result["calls"][-1]["body"]["history"]
    assert 0 < len(history) <= 20
    assert all(len(message["content"]) <= 4000 for message in history)
    assert sum(len(message["content"]) for message in history) <= 20000


def test_browser_keeps_resumed_clarification_in_history() -> None:
    frames = [
        {"type": "run_started", "run_id": "run-browser"},
        {"type": "run_result", "run_id": "run-browser", "result": {
            "status": "needs_clarification", "answer": None, "sources": [],
            "clarification": {"question": "Which saxophone?", "options": ["Alto", "Tenor"]},
        }},
        {"type": "run_completed", "run_id": "run-browser", "status": "needs_clarification"},
    ]
    result = _browser(
        frames=frames, chooseOption="Alto", resumeFrames=_frames("Alto is in E-flat."),
        followUps=["Which written key produces concert C major?"],
    )
    history = result["calls"][-1]["body"]["history"]
    assert any(message == {"role": "user", "content": "Alto"} for message in history)
    assert any(message == {"role": "assistant", "content": "Alto is in E-flat."} for message in history)


def test_browser_sends_clarification_choice_to_resume_route() -> None:
    frames = [
        {"type": "run_started", "run_id": "run-browser"},
        {"type": "run_result", "run_id": "run-browser", "result": {
            "status": "needs_clarification", "answer": None, "sources": [],
            "clarification": {"question": "Which triad?", "options": ["Major triad", "Minor triad"]},
        }},
        {"type": "run_completed", "run_id": "run-browser", "status": "needs_clarification"},
    ]
    result = _browser(
        frames=frames, chooseOption="Major triad", resumeFrames=_frames("Resumed answer [1].")
    )

    assert [call["url"] for call in result["calls"]] == [
        "/agent/chat/stream", "/agent/chat/runs/run-browser/resume",
    ]
    assert result["calls"][1]["body"] == {"option": "Major triad"}
    assert "Resumed answer [1]." in result["text"]


def test_browser_renders_validated_citation_images_and_keeps_answer_as_text() -> None:
    source = {
        "citation": "[7]", "source": "music.md", "chunk_id": "chunk-1",
        "paragraph_ref": "paragraph-1", "page_start": 1, "page_end": 1,
        "images": [{"url": "/api/v1/assets/images/triad.png", "alt": "Triad", "caption": "Triad"}],
    }
    answer = '<img src="bad" onerror="alert(1)"> [7]'
    result = _browser(frames=_frames(answer, source=source))

    assert answer in result["text"]
    assert result["imageCount"] == 1
    assert "[7]" in result["text"]


def test_browser_shows_inline_number_and_matching_document_page_below() -> None:
    source = {
        "citation": "[1]", "source": "music-theory-full", "chunk_id": "c-alto",
        "paragraph_ref": "p-alto", "page_start": 42, "page_end": 42,
    }
    result = _browser(frames=_frames("Alto is in E-flat [1].", source=source))
    assert "Alto is in E-flat [1]." in result["text"]
    assert "[1] music-theory-full" in result["text"]
    assert "trang 42" in result["text"]


def test_browser_shows_a_web_link_under_its_numeric_citation() -> None:
    source = {
        "citation": "[1]", "source": "Alto transposition guide", "chunk_id": "",
        "paragraph_ref": "", "page_start": None, "page_end": None,
        "url": "https://example.test/alto",
    }
    result = _browser(frames=_frames("Concert C is written A [1].", source=source))
    assert "Concert C is written A [1]." in result["text"]
    assert any(link["href"] == source["url"] for link in result["links"])


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,unsafe"])
def test_browser_does_not_turn_invalid_source_urls_into_links(url) -> None:
    source = {
        "citation": "[1]", "source": "Invalid link", "chunk_id": "",
        "paragraph_ref": "", "page_start": None, "page_end": None, "url": url,
    }
    result = _browser(frames=_frames("Answer [1].", source=source))
    assert not any(link["href"] == url for link in result["links"])


def test_browser_shows_live_processing_indicator_and_elapsed_timer_until_response_finishes() -> None:
    result = _browser(frames=_frames())
    assert result["calls"][0]["processing"] == "true"
    assert result["calls"][0]["activityVisible"] is True
    assert result["calls"][0]["activeTimerCount"] == 1
    assert result["processing"] == "false"
    assert result["activityHidden"] is True
    assert result["activeTimerCount"] == 0


def test_browser_stops_processing_indicator_and_timer_after_transport_failure() -> None:
    result = _browser(streamStatus=500)
    assert result["calls"][0]["processing"] == "true"
    assert result["processing"] == "false"
    assert result["activityHidden"] is True
    assert result["activeTimerCount"] == 0


def test_browser_resume_also_shows_processing_activity() -> None:
    frames = [
        {"type": "run_started", "run_id": "run-browser"},
        {"type": "run_result", "run_id": "run-browser", "result": {
            "status": "needs_clarification", "answer": None, "sources": [],
            "clarification": {"question": "Which saxophone?", "options": ["Alto", "Tenor"]},
        }},
        {"type": "run_completed", "run_id": "run-browser", "status": "needs_clarification"},
    ]
    result = _browser(frames=frames, chooseOption="Alto", resumeFrames=_frames("Alto is in E-flat [1]."))
    assert len(result["calls"]) == 2
    assert all(call["processing"] == "true" and call["activityVisible"] for call in result["calls"])
    assert result["activeTimerCount"] == 0
    assert result["activityHidden"] is True


def test_browser_internal_knowledge_answer_remains_visible_without_invented_sources() -> None:
    answer = "Tạm thời chưa tìm thấy đủ thông tin. Tôi sẽ dùng kiến thức nội tại để trả lời. Alto dùng giọng viết La trưởng."
    frames = _frames(answer)
    frames[-2]["result"]["answer_basis"] = "internal_knowledge"
    result = _browser(frames=frames)
    assert answer in result["text"]
    assert "nguồn đã sử dụng" not in result["text"]


def test_processing_animation_has_reduced_motion_support() -> None:
    stylesheet = (SCRIPT.parent / "chat.css").read_text()
    markup = (SCRIPT.parent / "index.html").read_text()
    assert 'id="request-activity"' in markup
    assert "@keyframes request-pulse" in stylesheet
    assert "prefers-reduced-motion" in stylesheet
