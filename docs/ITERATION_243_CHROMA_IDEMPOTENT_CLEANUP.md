# Iteration 243 – Cleanup Chroma idempotent

## Phạm vi

Khóa lifecycle cleanup của `ChromaVectorIndex` để shutdown không gọi lặp
`client.close()` khi composition root hoặc adapter gọi cả `close()` và `aclose()`.

## Thay đổi

- Thêm cờ trạng thái nội bộ `_closed`.
- `close()` trở thành idempotent; nếu thao tác đóng lần đầu ném lỗi thì trạng thái
  chưa đóng vẫn được giữ để caller có thể retry.
- Thêm contract test gọi tuần tự `close()`, `close()` và `aclose()`, xác nhận
  provider chỉ nhận đúng một lần gọi.

## Bằng chứng xác minh

```text
uv run pytest -q tests/test_phase_4_ingestion_contract.py -k "idempotent_across_sync_and_async_cleanup or aclose_runs_blocking_client_close"
2 passed, 98 deselected

uv run pytest -q
926 passed, 18 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Các test skip vẫn là giới hạn môi trường Windows hiện tại (thiếu Gradio,
sample source hoặc quyền tạo symbolic link). Live model-service smoke và
production parity vẫn chưa chạy vì checkout chưa có endpoint, credential và
production catalog thật.
