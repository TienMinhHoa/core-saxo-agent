# Iteration 68 — Contract ID xoá Chroma fail-closed

## Phạm vi

Siết boundary `ChromaVectorIndex.delete_chunks` theo yêu cầu adapter Chroma
trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: không cho phép ID rỗng,
sai kiểu hoặc truyền nhầm một chuỗi đơn lẻ đi tới lệnh xoá blocking.

## Thay đổi

- Thêm validation dùng chung cho danh sách ID xoá; chấp nhận `list`/`tuple`
  các chuỗi không blank và giữ nguyên ID hợp lệ.
- Reject trước provider I/O với `ValueError` khi input là chuỗi, có ID rỗng
  hoặc có phần tử không phải chuỗi.
- Giữ nguyên hành vi không gọi Chroma khi danh sách rỗng.
- Bổ sung 3 regression tests chứng minh malformed input không thể chạm tới
  collection `delete`.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q` →
  **30 passed**.
- Full suite: `uv run pytest -q` → **408 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt (chỉ còn cảnh báo line ending CRLF của Git trên
  hai file Python đã sửa).

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật. Iteration này
không thay đổi kiến trúc direct LiteLLM hoặc tạo job lifecycle.
