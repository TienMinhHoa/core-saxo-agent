# Iteration 214 — Đưa validation payload của `get()` vào bounded worker

## Mục tiêu

Tiếp tục thực hiện yêu cầu trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: filesystem
I/O và công việc blocking không được chạy trên event loop. Sau Iteration 212, việc
đọc file và kiểm tra path đã chạy trong bounded worker; iteration này hoàn tất cùng
ranh giới cho việc hash và kiểm tra checksum/kích thước của payload đọc được.

## Thay đổi

- `LocalArtifactRepository._read_artifact()` đọc file rồi gọi `_validate_payload()`
  bên trong worker do `anyio.to_thread.run_sync()` điều phối.
- `get()` chỉ nhận kết quả đã được kiểm tra từ worker, không lặp lại việc hash payload
  trên event-loop thread.
- Bổ sung contract test ghi nhận thread thực thi payload validation khác event-loop
  thread.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q --basetemp=.pytest-tmp-214`
  → **36 passed, 1 skipped**.
- Case symbolic link bị skip vì Windows runner không có privilege tạo symbolic link;
  các guard fail-closed còn lại vẫn được kiểm thử.

## Đối chiếu kiến trúc

Kết quả này đáp ứng quy tắc bounded executor của Phase 2 và mục tiêu runtime async:
đọc artifact, kiểm tra kích thước và SHA-256 đều nằm trong một bounded blocking-I/O
operation; application không đưa payload lớn và phép hash blocking trở lại event loop.

Full suite và `compileall` sẽ được chạy ở bước validation cuối của iteration.
