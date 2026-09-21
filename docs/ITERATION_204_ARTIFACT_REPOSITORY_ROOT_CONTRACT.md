# Iteration 204 — Contract kiểu runtime cho root của artifact repository

## Phạm vi

`LocalArtifactRepository` là storage adapter của backend và nhận `root: Path` tại
composition boundary. Trước thay đổi, type hint không được kiểm tra lúc runtime:
truyền `str`, `None` hoặc số nguyên làm phát sinh `AttributeError` tại `.resolve()`
thay vì một lỗi contract rõ ràng.

## Thay đổi

- Bổ sung fail-closed guard trong constructor: `root` phải là `pathlib.Path`.
- Bổ sung 3 regression tests cho `str`, `None` và `int`; guard chạy trước khi
  khởi tạo storage state.

## Bằng chứng kiểm chứng

- TDD red phase: 3 case mới thất bại với `AttributeError`, chứng minh lỗ hổng
  runtime contract.
- TDD green phase: `uv run pytest tests/test_phase_2_artifact_storage_contract.py
  -q --basetemp=.pytest-tmp-204` → **23 passed, 1 skipped**.
- `python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt; cảnh báo LF/CRLF chỉ do checkout Windows.

## Trạng thái còn lại

Đây là kiểm chứng offline. Live model-service smoke và production golden parity
vẫn chưa thể chạy vì checkout chưa có endpoint, credential và catalog production.
