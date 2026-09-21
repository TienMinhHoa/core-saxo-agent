# Iteration 210 - kiểm tra lại artifact root trước khi resolve

## Phạm vi

Tiếp tục harden `LocalArtifactRepository` theo yêu cầu file-safety của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Lát này xử lý trường hợp artifact
root đã bị thay đổi thành symbolic link sau khi repository được khởi tạo.

## Thay đổi

- `_path_for()` gọi lại `_reject_symbolic_link_in_path(self._root)` trước khi
  tạo hoặc resolve đường dẫn artifact.
- Thêm regression test mô phỏng root trở thành symbolic link sau constructor;
  repository phải fail-closed và không tạo artifact nào.

## Bằng chứng

- Test trước khi sửa: **1 failed**, đúng vì chưa có guard kiểm tra lại root.
- Test targeted sau khi sửa: **7 passed, 1 skipped**; test skip là do Windows
  checkout không có privilege tạo symbolic link thật.
- Full suite: **898 passed, 3 skipped, 1 warning**; `compileall` và
  `git diff --check` đều đạt.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì
checkout vẫn thiếu endpoint, credential và production catalog thật.
