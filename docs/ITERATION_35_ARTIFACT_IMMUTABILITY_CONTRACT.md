# Iteration 35 — Contract ghi artifact bất biến

## Phạm vi

Khóa một identity artifact (`artifact_id` + `version`) sau lần ghi đầu tiên.
Retry cùng metadata và cùng bytes vẫn idempotent; payload khác không được phép
ghi đè artifact đã tồn tại.

## Thay đổi

- `LocalArtifactRepository._write_atomically()` đọc artifact hiện có trong
  bounded filesystem I/O trước khi ghi.
- Bytes giống hệt được coi là retry an toàn.
- Bytes khác bị từ chối bằng `FileExistsError("artifact identity is immutable")`;
  không dùng `os.replace` để âm thầm thay thế dữ liệu đã phát hành.
- Bổ sung regression test cho cả retry idempotent và replacement bị từ chối.

## Bằng chứng kiểm chứng

- Red test trước implementation: **1 failed, 6 passed**, đúng tại assertion
  replacement phải bị từ chối.
- Sau implementation: targeted artifact storage test và full suite cần được
  chạy trong iteration này.

## Giới hạn còn lại

Live model-service smoke và production retrieval parity vẫn chưa thể xác minh
vì checkout chưa có endpoint, credential và catalog production thật.
