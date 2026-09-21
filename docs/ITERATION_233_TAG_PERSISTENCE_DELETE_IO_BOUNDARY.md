# Iteration 233 — bounded I/O khi xóa tag sidecar

## Phạm vi

Tiếp tục thực thi yêu cầu async boundary trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: filesystem blocking phải chạy
qua bounded thread executor. Scope chỉ gồm `JsonTaggedParagraphRepository.delete()`;
catalog và các repository khác không thay đổi.

## Thay đổi

- Thêm regression test kiểm tra `_path_for()` của thao tác `delete()` chạy trên
  worker thread, không chạy trên event loop.
- Đưa cả bước resolve path và `unlink()` vào helper đồng bộ `_delete()`, rồi
  gọi helper qua `anyio.to_thread.run_sync` với limiter đã inject.

Điểm quan trọng: chỉ offload `unlink()` vẫn chưa đủ, vì `_path_for()` có thể
kiểm tra filesystem để phát hiện symbolic link.

## Bằng chứng kiểm thử

Lệnh:

```text
uv run pytest tests/test_phase_8_tag_persistence_ports.py -q
```

Kết quả: **9 passed, 2 skipped**.

Hai test bị skip có kiểm soát vì tài khoản Windows hiện tại không có quyền
tạo symbolic link. Không có live model-service smoke trong iteration này.
