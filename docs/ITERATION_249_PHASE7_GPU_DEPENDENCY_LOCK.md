# Iteration 249 — khóa dependency GPU/model trong backend

## Mục tiêu

Khóa một tiêu chí Phase 7 trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
backend package và dependency lock không được kéo CUDA runtime, Paddle GPU hoặc
local model runtime vào ứng dụng.

## Thay đổi

- Bổ sung test `test_backend_dependency_manifests_do_not_lock_local_gpu_runtime`.
- Test quét `pyproject.toml`, `requirements.txt` và `uv.lock` theo danh sách tên
  dependency cấm; test không xem các dependency chuyển tiếp không phải GPU như
  `onnxruntime` là vi phạm.

## Bằng chứng

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py` — **11 passed**.
- Full suite: `uv run pytest` — **932 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ còn cảnh báo chuyển đổi newline CRLF tiêu chuẩn của
  Git trên Windows.
- Live model-service smoke và production parity vẫn chưa thể xác minh vì checkout
  không có endpoint, credential và production catalog thật.
