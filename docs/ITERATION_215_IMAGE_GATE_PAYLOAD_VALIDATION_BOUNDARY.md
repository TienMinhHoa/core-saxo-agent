# Iteration 215 - bounded payload validation cho image artifact gate

## Phạm vi

Tiếp tục thực hiện quy tắc async trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
mọi phép hash/checksum có thể xử lý payload lớn không được chạy trực tiếp trên
FastAPI event loop.

## Thay đổi

- `RepositoryBackedImageArtifactGate` nhận `CapacityLimiter` tùy chọn và tạo
  limiter bounded mặc định.
- Bước xác minh kích thước/SHA-256 sau khi repository trả image bytes chạy qua
  `anyio.to_thread.run_sync(..., limiter=...)`.
- Bổ sung contract test chứng minh checksum của image gate chạy trên worker
  thread, đồng thời giữ nguyên kiểm tra kind/media type và tampered payload.

## Bằng chứng kiểm thử

- Targeted: `4 passed` với `tests/test_phase_6_image_artifact_repository_gate.py`.
- Full suite: `903 passed, 3 skipped, 1 warning`.
- Một test symbolic link tiếp tục skip trên Windows vì runner không có quyền
  tạo symbolic link (`WinError 1314`).

## Giới hạn xác minh

Live model-service smoke và production parity chưa chạy vì checkout không có
endpoint, credential và production catalog được phê duyệt.
