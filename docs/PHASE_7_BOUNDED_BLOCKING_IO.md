# Giới hạn I/O blocking trong async adapter

## Kết quả

Các adapter Chroma nhận một `anyio.CapacityLimiter`; nếu không truyền vào, mỗi
adapter dùng limiter mặc định 8 tác vụ blocking đồng thời.

## Quy tắc

- Call Chroma và embedding blocking vẫn chạy ngoài event loop qua
  `anyio.to_thread.run_sync`.
- Mọi call của cùng adapter dùng chung limiter cho `get`, `upsert`, `delete`,
  `query` và embedding.
- Capacity không hợp lệ bị từ chối sớm; không có fallback im lặng.

## Bằng chứng iteration

- `uv run pytest -q tests/test_phase_7_bounded_blocking_io.py tests/test_chroma_semantic_retriever.py tests/test_phase_4_index_document.py`: 19 passed.
- `uv run pytest -q`: 253 passed, 2 skipped, 1 warning.
- `python -m compileall -q src tests` và `git diff --check`: đạt.
- Live Chroma và production multi-worker smoke test chưa được xác minh.
