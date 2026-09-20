# Iteration 97 — Contract bounded I/O cho reconcile và delete Chroma

## Phạm vi

Tiếp tục hướng Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, iteration này
khóa bằng test yêu cầu mọi thao tác blocking của Chroma adapter đều đi qua cùng
bounded I/O limiter. Phạm vi chỉ gồm hai thao tác còn thiếu regression coverage trực tiếp:
`list_chunk_ids()` và `delete_chunks()`.

## Thay đổi

- Bổ sung contract test chứng minh thao tác reconcile (`collection.get`) dùng limiter
  được inject vào `ChromaVectorIndex`.
- Bổ sung cùng contract cho thao tác xóa (`collection.delete`).
- Không đổi production logic vì implementation hiện tại đã đáp ứng yêu cầu; test mới
  bảo vệ ranh giới async adapter khỏi việc gọi SDK blocking trực tiếp trong event loop.

## Bằng chứng xác minh

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -k "blocking_io_limiter or reconcile_and_delete" --basetemp=.pytest-tmp`.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi.
- Live model-service smoke và production golden parity chưa xác minh vì checkout vẫn
  thiếu endpoint, credential và catalog production được phê duyệt.

## Trạng thái

Contract bounded I/O cho cả search, reconcile và delete đã có regression coverage offline.
