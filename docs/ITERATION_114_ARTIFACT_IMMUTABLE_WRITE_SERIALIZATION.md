# Iteration 114 - tuần tự hóa ghi artifact immutable

## Phạm vi

Đóng một race condition trong `LocalArtifactRepository`: hai request đồng thời
ghi cùng `artifact_id/version` không được phép cùng thấy đường dẫn chưa tồn tại
rồi thay thế artifact của nhau.

## Thay đổi

- Thêm `threading.Lock` ở repository boundary và giữ lock xuyên suốt thao tác
  kiểm tra artifact hiện hữu, ghi file tạm và `os.replace`.
- Giữ nguyên idempotency: cùng payload vẫn thành công; payload khác vẫn nhận
  `FileExistsError`.
- Thêm contract test chạy hai `put()` đồng thời và kiểm tra chỉ một payload được
  commit, payload còn lại không thể thay thế artifact immutable.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_2_artifact_storage_contract.py`.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi.

Đây là kiểm thử offline. Live model-service smoke và production golden parity
vẫn chưa thể xác minh vì checkout chưa được cấp endpoint, credential và catalog
production.
