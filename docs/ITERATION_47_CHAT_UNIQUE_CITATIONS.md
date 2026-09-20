# Iteration 47 - Chuẩn hóa citation không trùng ở ChatResult

## Phạm vi

Khóa một khe nhỏ tại chat boundary: `AnswerQuestion` đã loại citation trùng,
nhưng `ChatResult` vẫn có thể được khởi tạo trực tiếp với cùng một source ref
nhiều lần. DTO cuối cần tự bảo vệ invariant để mọi caller đều nhận contract
nhất quán.

## Thay đổi

- Thêm validation trong `src/saxophone/chat/models.py`: danh sách `citations`
  phải chứa các source ref duy nhất.
- Thêm regression test TDD trong `tests/test_chat_answer_question.py` cho
  citation trùng bị từ chối.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_chat_answer_question.py -q` — **11 passed**.
- Full suite: `uv run pytest -q` — **343 passed, 2 skipped, 1 warning**.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` đều đạt;
  `git diff --check` chỉ phát cảnh báo chuyển đổi LF/CRLF của Git.

## Giới hạn xác minh

Slice này chỉ xác minh contract offline. Live model-service smoke và golden
parity production vẫn chưa thể chạy do checkout chưa có endpoint, credential và
production catalog thật.
