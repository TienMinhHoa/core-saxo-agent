# Iteration 99 — Bounded I/O cho tag persistence

## Phạm vi

Theo yêu cầu async trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, hai
filesystem adapter của topic tagging không được gọi blocking I/O bằng
`asyncio.to_thread` không giới hạn.

## Thay đổi

- `JsonTaggedParagraphRepository` và `JsonTagCatalogRepository` nhận
  `anyio.CapacityLimiter` tùy chọn; nếu không inject thì tự tạo limiter mặc định.
- Các thao tác đọc, ghi và xóa JSON chạy qua `anyio.to_thread.run_sync(...,
  limiter=...)`.
- Composition root truyền cùng shared limiter cho hai tag repository, embedding
  reuse store, artifact repository và Chroma adapter.
- Bổ sung contract test chứng minh limiter được nhận đúng và composition root
  không tạo limiter riêng cho từng tag repository.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_8_tag_persistence_ports.py tests/test_phase_1_composition_root.py -q`
  — **35 passed**, 1 warning deprecation từ Starlette.
- Full suite: `491 passed, 2 skipped, 1 warning`.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ có cảnh báo chuyển đổi LF/CRLF của Git trên Windows.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout chưa có endpoint, credential và catalog production được phê duyệt.

## Kết luận

Lát refactor này hoàn tất contract bounded filesystem I/O cho persistence của
topic tagging mà không thay đổi port hoặc format JSON hiện hữu.
