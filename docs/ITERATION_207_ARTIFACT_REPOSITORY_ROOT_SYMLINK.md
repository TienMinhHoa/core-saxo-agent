# Iteration 207 — chặn symbolic link tại artifact root

## Phạm vi

Theo hướng Clean Code của kế hoạch refactor, iteration này harden một contract
nhỏ tại biên `LocalArtifactRepository`: thư mục root do backend sở hữu không được
là symbolic link.

## Thay đổi

- Constructor kiểm tra `root.is_symlink()` trước khi gọi `resolve()`.
- Nếu root là symbolic link, constructor fail-fast bằng `ValueError` với thông
  báo `root must not be a symbolic link`.
- Bổ sung regression test dùng monkeypatch để kiểm chứng contract ngay cả trên
  Windows không có quyền tạo symbolic link.

## Lý do an toàn

Nếu resolve symbolic link trước khi kiểm tra, cấu hình root có thể trỏ ngầm sang
một thư mục khác với root mà operator đã kiểm soát. Từ chối ngay tại boundary
giữ cho mapping artifact identity → filesystem root tường minh và fail-closed.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q`
  → **29 passed, 1 skipped**; test skip là case tạo symbolic link thật bị
  Windows từ chối vì thiếu privilege.
- `uv run pytest -q`
  → **895 passed, 3 skipped, 1 warning**.
- `compileall` và `git diff --check` được chạy sau thay đổi.

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và production catalog thật.
