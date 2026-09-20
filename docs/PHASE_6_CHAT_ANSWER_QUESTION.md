# Phase 6 Chat - `AnswerQuestion`

## Phạm vi lát cắt

Iteration này chọn phương án Clean Code cho lát cắt nhỏ đầu tiên của Phase 6:
đưa luồng hỏi đáp vào use case `AnswerQuestion`, chỉ cho phép answer generator
nhận `EvidenceBundle` đã được retrieval validate. Chat không import Chroma,
HTTP client, model SDK hay GPU transport.

## Thay đổi

- `saxophone.chat.models` định nghĩa `ChatStatus`, `GeneratedAnswer` và
  `ChatResult`; DTO chỉ trả answer/citations/usage, không chứa chain-of-thought.
- `AnswerGenerator` là application port bất đồng bộ, tách prompt/provider adapter
  khỏi use case.
- `AnswerQuestion` gọi `RetrieveEvidence`, trả `insufficient_evidence` rõ ràng
  và không gọi LLM khi không có hit; khi có evidence, citations được suy ra từ
  `source_ref` và tạo reference ổn định cho evidence bundle.
- Test dùng fake retriever/generator để khóa happy path, thiếu evidence và lỗi
  validation usage/answer.

## Bằng chứng kiểm chứng

- Targeted contract tests: `3 passed` (`tests/test_chat_answer_question.py`).
- Full offline suite: `108 passed, 2 skipped, 1 warning`.
- `python -m compileall -q src tests` và `git diff --check` đều đạt.
- Chưa tuyên bố live model/provider, artifact image gate hoặc FastAPI route; các
  phần đó thuộc các lát cắt tiếp theo của Phase 6.
