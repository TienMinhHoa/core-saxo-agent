# Iteration 96 — Contract đầu vào cho Chroma upsert

## Phạm vi

Tiếp tục hướng Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, tập trung
vào ranh giới `VectorIndex.upsert_chunks`. Adapter phải từ chối dữ liệu không đúng
contract trước khi gọi SDK Chroma blocking.

## Thay đổi

- `ChromaVectorIndex.upsert_chunks()` yêu cầu `records` là một `Sequence`, đồng thời
  loại trừ chuỗi/bytes để tránh coi từng ký tự là record.
- Mọi phần tử phải là `ChunkIndexRecord`; input sai bị fail-closed bằng `ValueError`.
- Bổ sung regression tests chứng minh provider không bị gọi khi input sai kiểu.

## Bằng chứng xác minh

- `uv run pytest tests/test_phase_4_ingestion_contract.py -k "chroma_upsert" --basetemp=.pytest-tmp`
  — 19 passed, 69 deselected.
- Full suite, `compileall` và `git diff --check` được chạy sau khi hoàn tất thay đổi.

## Trạng thái

Đơn vị contract này đã hoàn tất offline. Live model-service smoke và production
parity vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và catalog
production được phê duyệt.
