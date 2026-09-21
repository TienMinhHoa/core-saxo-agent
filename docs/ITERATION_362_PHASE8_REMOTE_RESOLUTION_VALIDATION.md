# Iteration 362 - validation output remote conflict resolution Phase 8

## Phạm vi

Tiếp tục Phase 8 theo hướng Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Slice này khóa boundary của `RemoteTagConflictResolver`: mọi output resolution
không hợp lệ từ model phải được chuẩn hóa thành `ModelValidationError`, thay vì để
`ValueError` nội bộ của DTO thoát ra ngoài adapter.

## Thay đổi

- Thêm regression test cho ba dạng output không hợp lệ: `action` ngoài contract,
  `generated_tag` rỗng và `resolved_tag` rỗng.
- Adapter giữ nguyên `ModelValidationError` đã có từ bước parse bắt buộc; đồng thời
  bọc `ValueError` phát sinh khi dựng `TagResolution` hoặc `TagConflictResolution`
  thành lỗi boundary có kiểu thống nhất.
- Không thêm fallback hoặc tự sửa output model; dữ liệu sai vẫn fail-closed.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_8_remote_tagging.py tests/test_phase_8_conflict_resolution_contract.py -q
15 passed
```

Full suite và live model-service smoke chưa chạy trong slice này; production parity
vẫn cần endpoint, credential và production catalog thật.

## Kết luận

Remote tagging boundary hiện không để lộ lỗi `ValueError` nội bộ khi model trả
resolution sai schema/domain; caller nhận được `ModelValidationError` nhất quán.
