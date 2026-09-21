# Iteration 278 - facade công khai cho workflow ingestion

## Phạm vi

Workflow `IngestExtractedDocument` là application orchestration. Workflow này
không nên biết các module triển khai nội bộ của ingestion (`chunking`, `models`
hoặc `use_cases`). Slice này chỉ khóa một ranh giới dependency nhỏ, không thay
đổi contract xử lý Markdown, tagging, embedding hay indexing.

## Thay đổi

- Thêm contract test AST bảo đảm workflow không import trực tiếp các module
  triển khai ingestion.
- Chuyển các symbol workflow cần dùng sang facade ổn định `saxophone.ingestion`.

## Bằng chứng kiểm tra

- Contract Phase 7: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q` đạt
  **37 passed**.
- Full suite: `uv run pytest -q` đạt **963 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` thành công.
- `git diff --check` không phát hiện lỗi whitespace; chỉ có cảnh báo chuyển đổi
  dòng LF/CRLF theo môi trường Windows.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout không có endpoint, credential và catalog production thật.
