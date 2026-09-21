# Iteration 280 - guard facade cho toàn bộ contract của API

## Phạm vi

Inbound adapter `saxophone.interfaces.api` đã dùng facade công khai cho chat,
ingestion, retrieval và workflows. Tuy nhiên guard Phase 7 chưa kiểm tra riêng
việc API có quay lại import implementation nội bộ của documents, extraction
hoặc tagging hay không.

## Thay đổi

- Bổ sung AST contract test cho toàn bộ nhóm implementation prefix của
  documents, extraction và tagging.
- Giữ nguyên source runtime; test xác nhận API chỉ nhận contract qua các facade
  `saxophone.documents`, `saxophone.extraction` và `saxophone.tagging`.

## Bằng chứng kiểm tra

- Phase 7 dependency tests: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`.
- Full offline suite: `uv run pytest -q`.
- Kiểm tra cú pháp: `python -m compileall -q src tests`.
- Kiểm tra whitespace: `git diff --check`.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout không có endpoint, credential và catalog production thật.
