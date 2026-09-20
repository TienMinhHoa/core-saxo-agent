# Iteration 100 — wiring KnowledgeRepository trong composition root

## Phạm vi

Đã hoàn tất một đơn vị nhỏ còn thiếu của kiến trúc trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `JsonKnowledgeRepository` được
tạo tại composition root, dùng chung bounded I/O limiter với artifact/tag/cache
repositories, và được truyền vào `IndexDocument`.

Điều này bảo đảm pipeline ingestion ghi metadata knowledge full-fidelity trước
khi publish projection searchable vào Chroma; vector index không còn là nơi
duy nhất giữ dữ liệu chunk.

## Thay đổi

- `AppContainer` expose `KnowledgeRepository` để kiểm tra wiring runtime.
- `AppOverrides` cho phép thay thế repository trong test hoặc deployment.
- Production composition mặc định dùng `data_root / "knowledge"` và shared
  `CapacityLimiter`.
- Regression test xác nhận adapter, limiter dùng chung với artifact repository,
  và `IndexDocument` nhận đúng dependency.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_1_composition_root.py tests/test_phase_4_ingest_extracted_document.py -q`
  → **35 passed, 1 warning**.
- `git diff --check` → đạt; chỉ còn cảnh báo line-ending LF/CRLF của Git trên
  Windows, không có whitespace error.

## Giới hạn còn lại

Iteration này không chạy live model-service hoặc production golden parity vì
checkout vẫn chưa có endpoint, credential và catalog production thật. Đây là
blocker môi trường đã được ghi nhận từ các iteration trước, không được thay thế
bằng fake HTTP smoke.
