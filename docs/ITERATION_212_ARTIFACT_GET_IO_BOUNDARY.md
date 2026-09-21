# Iteration 212 — Đưa kiểm tra artifact vào bounded I/O worker

## Phạm vi

Tiếp tục hardening `LocalArtifactRepository` theo yêu cầu async và file safety
trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Lát này chỉ xử lý đường
đọc artifact (`get`).

## Thay đổi

- `get()` không còn gọi `_path_for()` trên event loop.
- `_path_for()` và thao tác đọc file được gom vào `_read_artifact()` và chạy qua
  `anyio.to_thread.run_sync(..., limiter=self._io_limiter)`.
- Thêm contract test xác nhận path validation chạy trên worker thread, không
  chạy trên caller/event-loop thread.

Điều này giữ filesystem validation cùng boundary với blocking read và tái sử
dụng cùng `CapacityLimiter` của repository.

## Bằng chứng

- Red test trước implementation: `1 failed, 33 passed, 1 skipped`.
- Targeted sau implementation: `34 passed, 1 skipped`.
- Skip là test symbolic link thật trên Windows vì môi trường thiếu privilege
  tạo symbolic link (`WinError 1314`); các guard fail-closed vẫn được kiểm tra
  bằng monkeypatch.

## Giới hạn xác minh

Iteration này chưa chạy live model-service smoke hoặc production parity vì
checkout vẫn không có endpoint, credential và production catalog được phê
duyệt.
