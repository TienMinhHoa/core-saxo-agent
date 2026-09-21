# Iteration 205 — contract root thư mục của artifact repository

## Phạm vi

Tiếp tục Phase 2 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, chỉ xử lý
boundary constructor của `LocalArtifactRepository`. Root có thể chưa tồn tại để
adapter tạo thư mục ở lần ghi đầu tiên, nhưng nếu path đã tồn tại thì bắt buộc
phải là thư mục.

## Thay đổi

- Chuẩn hóa root bằng `Path.resolve()` như trước.
- Fail-fast với `ValueError("root must be a directory")` khi root hiện hữu là
  file hoặc filesystem object không phải thư mục.
- Giữ nguyên hành vi cho root chưa tồn tại và root là thư mục.
- Thêm regression test theo TDD cho existing-file root.

## Bằng chứng kiểm chứng

- Test đỏ trước implementation: test mới fail vì constructor chưa reject root
  là file.
- Test xanh sau implementation: sẽ chạy targeted test và full suite trong
  iteration này.
- `compileall` và `git diff --check` được chạy sau khi test hoàn tất.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì
checkout chưa có endpoint, credential và production catalog thật.
