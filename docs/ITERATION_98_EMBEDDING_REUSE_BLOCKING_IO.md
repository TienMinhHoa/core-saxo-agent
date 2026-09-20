# Iteration 98 — Bounded I/O cho embedding reuse store

## Phạm vi

Theo yêu cầu async trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, iteration
này xử lý một lát cắt nhỏ của filesystem adapter: `FileEmbeddingReuseStore`
không được gọi filesystem blocking mà không qua limiter.

## Thay đổi

- Bổ sung tham số `io_limiter` tùy chọn cho `FileEmbeddingReuseStore`; nếu không
  inject thì adapter tự tạo limiter mặc định để không phá vỡ caller hiện tại.
- `find()` và `save()` truyền cùng limiter vào `anyio.to_thread.run_sync`.
- Composition root truyền shared limiter dùng chung với artifact repository và
  Chroma index vào embedding reuse store.
- Bổ sung contract test chứng minh cả đường đọc và ghi đều nhận đúng limiter.

## Bằng chứng kiểm chứng

- TDD red trước implementation: test mới fail vì constructor chưa nhận
  `io_limiter` (`TypeError`), xác nhận test bắt đúng khoảng trống.
- Targeted: `uv run pytest tests/test_phase_4_index_document.py -k
  "shared_limiter_to_blocking_io or file_embedding_reuse_store" -q
  --basetemp=.pytest-tmp` — **4 passed**.
- Composition root: `uv run pytest tests/test_phase_1_composition_root.py -k
  "embedding_reuse" -q --basetemp=.pytest-tmp` — **1 passed**.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout không có endpoint, credential và catalog production được phê duyệt.
