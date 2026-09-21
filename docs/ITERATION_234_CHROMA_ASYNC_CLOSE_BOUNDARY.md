# Iteration 234 — đóng Chroma không chặn event loop

## Phạm vi

Đơn vị refactor nhỏ của iteration này là lifecycle cleanup của `ChromaVectorIndex`.
Các thao tác `get`, `upsert`, `delete` và `query` đã chạy qua bounded worker, nhưng
`close()` vẫn gọi SDK blocking trực tiếp. Điều này làm hở quy tắc async tại shutdown.

## Thay đổi

- Thêm `ChromaVectorIndex.aclose()` để đóng client qua `anyio.to_thread.run_sync`.
- Dùng chung `io_limiter` với các thao tác Chroma khác, nhờ đó giới hạn cả cleanup
  blocking trong cùng ngân sách worker.
- Giữ `close()` synchronous để không phá compatibility của caller cũ; composition
  root async nên dùng `await index.aclose()`.
- Thêm contract test xác minh client được đóng và limiter được truyền đúng qua
  worker boundary.

## Bằng chứng kiểm thử

- Targeted contract test: `99 passed` với
  `uv run pytest tests/test_phase_4_ingestion_contract.py -q`.
- Full suite: `919 passed, 18 skipped, 1 warning` với `uv run pytest -q`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.
- Các test symbolic link bị skip vì Windows account hiện tại thiếu quyền tạo
  symbolic link (`WinError 1314`), không phải lỗi của thay đổi này.

## Đối chiếu yêu cầu kiến trúc

Thay đổi này thực thi mục 12.1–12.2 của
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: SDK Chroma blocking phải chạy qua
bounded thread executor và lifecycle của adapter phải có contract test.
