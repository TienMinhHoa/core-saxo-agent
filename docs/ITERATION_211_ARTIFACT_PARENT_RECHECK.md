# Iteration 211 - kiểm tra lại parent artifact sau khi tạo thư mục

## Phạm vi

Tiếp tục harden `LocalArtifactRepository` theo yêu cầu artifact storage an
toàn trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Lát này xử lý khe hở
giữa lần kiểm tra symbolic link ban đầu và thao tác `mkdir` tạo parent
directory.

## Thay đổi

- Sau `path.parent.mkdir(...)`, repository gọi lại `_path_for(artifact)`
  trước khi tạo temporary file.
- Nếu parent path bị thay đổi thành symbolic link trong khoảng thời gian đó,
  repository fail-closed và không bắt đầu ghi payload.
- Thêm regression test mô phỏng parent trở thành symbolic link ngay sau khi
  tạo directory.

## Bằng chứng

- Test trước khi sửa: **1 failed**, chứng minh guard sau `mkdir` còn thiếu.
- Test targeted sau khi sửa: **33 passed, 1 skipped**; test skip là do
  Windows checkout không có privilege tạo symbolic link thật.
- Cần chạy full suite và `compileall` ở bước xác minh cuối iteration.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì
checkout vẫn thiếu endpoint, credential và production catalog thật.
