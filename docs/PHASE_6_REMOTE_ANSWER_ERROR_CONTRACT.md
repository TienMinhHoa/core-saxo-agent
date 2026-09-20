# Phase 6 — Hợp đồng lỗi typed cho answer model adapter

## Phạm vi

Lát cắt này chuẩn hóa mọi lỗi khi `RemoteAnswerGenerator` nhận response không
hợp lệ từ model service thành `ModelValidationError`. Adapter không để lộ
`ValueError` nội bộ của DTO `GeneratedAnswer` ra ngoài model boundary.

## Thay đổi

- Sai `task` hoặc `response_schema` trả về `ModelValidationError`.
- Thiếu/sai kiểu `answer`, `token_usage` hoặc `cost` trả về cùng loại lỗi.
- Lỗi validation phát sinh bên trong `GeneratedAnswer` được bọc lại với ngữ
  cảnh `model output violates answer contract`, giữ nguyên nguyên nhân gốc.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_remote_answer_generator.py`: **3 passed**.
- `uv run pytest tests/test_phase_4_index_document.py tests/test_remote_answer_generator.py`: **19 passed**.
- `uv run python -m compileall -q src`: đạt.
- `git diff --check`: đạt.

Toàn bộ suite đã chạy với kết quả **264 passed, 2 skipped, 1 failed** do test
đồng thời của `FileEmbeddingReuseStore` gặp `PermissionError` Windows khi
flush lock file; chạy lại nhóm liên quan ngay sau đó đạt 19/19. Đây là lỗi
môi trường/đồng thời không liên quan lát cắt answer adapter và cần được theo
dõi riêng ở iteration sau.
