# Iteration 113 — runtime boundary của artifact repository

## Phạm vi

Tiếp tục hardening contract `ArtifactRepository` theo hướng Clean Code
fail-closed: `LocalArtifactRepository.put()` và `get()` phải từ chối object không
phải `ArtifactRef` ngay tại boundary, trước khi truy cập thuộc tính identity hoặc
filesystem.

## Thay đổi

- Bổ sung guard runtime dùng chung `_require_artifact_ref()` cho cả `put()` và
  `get()`.
- Bổ sung regression test cho cả hai method, đồng thời xác nhận root tạm không
  phát sinh file/thư mục khi input sai.

## Bằng chứng kiểm thử

- Targeted contract: `uv run pytest tests/test_phase_2_artifact_storage_contract.py`
  — **11 passed**.
- Full suite, compileall và `git diff --check` được chạy sau thay đổi; kết quả
  được ghi ở handoff của iteration này.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity
vẫn chưa thể chạy vì checkout chưa có endpoint, credential và catalog production
được cấp phép.
