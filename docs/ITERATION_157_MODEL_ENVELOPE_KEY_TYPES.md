# Iteration 157 — Kiểu khóa mapping trong model envelope

## Phạm vi

Khóa các mapping top-level của `ModelRequest` (`input`, `metadata`) và
`ModelResponse` (`output`) phải là chuỗi. Đây là bước hardening nhỏ của hợp đồng
model-service trong mục 12.5 của kế hoạch kiến trúc.

## Thay đổi

- `_immutable_mapping` từ chối mapping có khóa không phải `str` bằng
  `ModelValidationError`.
- Bổ sung regression test cho `input`, `metadata` và `output`.
- Không thay đổi các mapping lồng nhau; chúng vẫn là dữ liệu task-specific và
  được adapter tương ứng kiểm tra.

## Bằng chứng xác minh

- Test tập trung: `19 passed`.
- Full suite: `684 passed, 3 skipped, 1 warning`.
- Các test vẫn chạy offline; live model-service smoke và production parity chưa
  thể xác minh vì checkout chưa có endpoint, credential và catalog production.
