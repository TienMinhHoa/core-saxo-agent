# Iteration 31 — contract bounded filesystem I/O

## Phạm vi

Khóa trước một contract nhỏ cho `LocalArtifactRepository`: các thao tác ghi
filesystem blocking phải nhận `CapacityLimiter`, tương tự adapter Chroma, để
không tạo không giới hạn worker khi nhiều request upload chạy đồng thời.

## Thay đổi

- Bổ sung contract test chạy hai lệnh `put` đồng thời với limiter có capacity 1.
- Test đo `peak` số thao tác blocking cùng lúc và yêu cầu giá trị bằng 1.
- Chưa sửa implementation trong iteration này; theo TDD, test đang là tiêu chí
  đỏ để iteration kế tiếp triển khai constructor và `anyio.to_thread.run_sync`
  có limiter.

## Bằng chứng

- Lệnh: `uv run pytest tests/test_phase_2_artifact_storage_contract.py::test_local_repository_bounds_concurrent_blocking_writes -q`
- Kết quả: **1 failed** tại contract mới vì `LocalArtifactRepository` hiện chưa
  nhận tham số `io_limiter` (`TypeError`). Đây là failure dự kiến, xác nhận test
  đang bắt đúng gap thay vì hiện trạng vô tình xanh.

## Còn lại

Iteration kế tiếp cần triển khai bounded limiter cho `put` và `get`, chạy lại
targeted test rồi full suite, `compileall` và `git diff --check`.
