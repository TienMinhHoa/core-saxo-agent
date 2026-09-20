# Iteration 195 — Safe-path contract cho Windows

## Phạm vi

Siết `AppSettings` theo hướng Clean Code ở boundary cấu hình: từ chối path
Windows dạng drive-relative như `C:relative`. Dạng này không trỏ tới một vị trí
cố định; Windows có thể diễn giải nó theo thư mục hiện tại của riêng drive `C:`.
Path root-relative cũng bị từ chối để tránh cách diễn giải phụ thuộc drive hiện
tại. Absolute path hợp lệ và relative path không chứa parent traversal vẫn được
giữ tương thích.

## Thay đổi

- `AppSettings.__post_init__` fail-closed khi nhận `Path` drive-relative hoặc
  root-relative.
- Parser environment trả lỗi gắn với đúng tên biến `SAXO_DATA_ROOT` hoặc
  `SAXO_CHROMA_PERSIST_DIRECTORY` trước khi tạo settings.
- Bổ sung regression tests cho direct construction và environment parsing.

## Bằng chứng

- TDD red trước implementation: 4 test mới fail vì path `C:relative` được chấp
  nhận.
- TDD green sau implementation: `uv run pytest -q tests/test_phase_1_settings.py
  -k "ambiguous_windows or drive_relative"` — **4 passed**.
- Full suite, compileall và `git diff --check` được chạy sau thay đổi; kết quả
  ghi ở handoff của iteration này.

## Giới hạn

Đây là kiểm chứng offline. Live model-service smoke và production parity vẫn
cần endpoint, credential và catalog production thật.
