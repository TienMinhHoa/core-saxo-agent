# Iteration 44 — validation citations tại boundary chat

## Phạm vi

Theo hướng Clean Code, gia cố DTO `ChatResult` tại boundary retrieval → chat.
Field `citations` được khai báo là `tuple[str, ...]`, vì vậy runtime contract
phải từ chối list mutable và chuỗi đơn lẻ thay vì để dữ liệu sai kiểu đi tiếp.

## Thay đổi

- `ChatResult.__post_init__` từ chối `citations` không phải tuple.
- Bổ sung regression tests cho list mutable và string không đúng kiểu.
- Không thay đổi format citation hợp lệ do use case hiện tại vẫn truyền tuple.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_chat_answer_question.py` — **8 passed**.
- Full suite: `uv run pytest` — **340 passed, 2 skipped, 1 warning**.
- Syntax: `uv run python -m compileall -q src tests` — đạt.
- Hygiene: `git diff --check` — đạt.

Các kiểm tra trên là offline; live model-service smoke và production golden
parity vẫn cần endpoint, credential và catalog production thật.
