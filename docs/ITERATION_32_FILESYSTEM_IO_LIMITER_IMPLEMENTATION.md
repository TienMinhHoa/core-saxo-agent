# Iteration 32 — triển khai bounded filesystem I/O

## Phạm vi

Theo contract TDD đã được tạo ở Iteration 31, hoàn thiện `LocalArtifactRepository`
để mọi thao tác filesystem blocking chạy qua `anyio.to_thread` với
`CapacityLimiter`. Chọn hướng Clean Code: limiter được tạo tại composition root
và chia sẻ cho artifact storage cùng Chroma adapter.

## Thay đổi

- `LocalArtifactRepository` nhận `io_limiter` tùy chọn và tạo limiter mặc định
  nếu adapter được dùng độc lập.
- `put` và `get` dùng `anyio.to_thread.run_sync(..., limiter=...)`; atomic write,
  checksum, kích thước payload và safe-path policy vẫn được giữ nguyên.
- `create_app` tạo một limiter bounded và truyền cùng instance vào local artifact
  repository và Chroma vector index.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py tests/test_phase_7_bounded_blocking_io.py -q --basetemp=.pytest-tmp`:
  **8 passed**.
- `uv run pytest -q --basetemp=.pytest-tmp`: **326 passed, 2 skipped, 1 warning**.
- `git diff --check`: đạt.
- Không chạy live model-service smoke vì checkout vẫn chưa có endpoint, credential
  và production catalog được phê duyệt.

## Kết luận lát cắt

Contract giới hạn đồng thời filesystem đã được triển khai và kiểm chứng offline.
Stop condition toàn bộ architecture plan chưa đạt do live model-service smoke và
production retrieval parity vẫn còn blocker môi trường.
