# Iteration 294 — bảo vệ typing runtime của callback UI

## Phạm vi

Tiếp tục Phase 7 theo hướng Clean Code: giữ `app.py` là composition/root entrypoint
cho UI tương thích, nhưng bảo đảm callback bên trong có đủ dependency runtime.

## Thay đổi

- Bổ sung `Any` từ `typing` vào `app.py`.
- Thêm contract test tại `tests/test_phase_7_legacy_ui_boundary.py` để ngăn callback
  dùng tên typing runtime mà không import.

## Bằng chứng

- Trước sửa, targeted test tái hiện đúng lỗi: `1 failed, 5 passed`; assertion xác
  nhận `Any` chưa nằm trong import của `app.py`.
- Sau sửa, chạy lại targeted test và full suite.
- Không thực hiện live model-service smoke vì checkout vẫn thiếu endpoint, credential
  và production catalog được phê duyệt.

## Kết luận

Callback `ask_answer()` không còn phụ thuộc vào tên `Any` chưa được định nghĩa khi
được gọi runtime. Đây là thay đổi nhỏ, không đổi contract UI hay kiến trúc module.
