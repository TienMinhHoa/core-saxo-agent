# Bằng chứng Phase 7: cache capability health

## Phạm vi

Iteration 71 chọn lát cắt Clean Code nhỏ nhất còn thiếu của mục 17.3 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: health endpoint không được gọi model
service cho từng request client. Cache nằm ở composition boundary, bọc mọi
`RemoteGpuGateway` (kể cả fake override trong test), nên HTTP adapter vẫn chỉ
chịu trách nhiệm gọi provider và chuẩn hóa DTO.

## Thay đổi

- Thêm `CachedRemoteGpuGateway` với TTL dương, đồng hồ monotonic và `asyncio.Lock`
  để tránh nhiều request đồng thời cùng gọi health upstream.
- Thêm cấu hình `SAXO_REMOTE_GPU_HEALTH_CACHE_SECONDS`, mặc định 5 giây; giá trị
  không hợp lệ bị từ chối khi parse settings.
- Composition root tự động bọc gateway trước khi health route sử dụng.

## Bằng chứng kiểm thử

- Test cache hit và refresh sau khi TTL hết: `tests/test_phase_1_remote_gpu_http.py`.
- Toàn bộ test offline, `compileall` và `git diff --check` cần được chạy ở cuối
  iteration; live model-service chưa được xác minh trong môi trường này.

## Giới hạn còn lại

Cache hiện chỉ tồn tại trong process backend; chưa có yêu cầu chia sẻ cache giữa
nhiều worker. Health vẫn không tiết lộ bearer token, provider payload hoặc path
cục bộ.
