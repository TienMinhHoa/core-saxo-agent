# Iteration 197 — canonical path contract của `AppSettings`

## Phạm vi

Đồng bộ contract giữa hai cách tạo cấu hình: `from_environment()` đã loại bỏ
whitespace ở đầu/cuối path, còn khởi tạo `AppSettings` trực tiếp trước đây vẫn
cho phép giữ lại giá trị không canonical.

## Thay đổi

- Bổ sung kiểm tra fail-closed trong `_validate_runtime_path()` để từ chối
  `data_root` và `chroma_persist_directory` có whitespace ở đầu/cuối.
- Bổ sung 2 regression tests TDD cho cả hai field path.
- Không thay đổi path hợp lệ có whitespace ở giữa; không thay đổi behavior
  parser environment vốn đã chuẩn hóa giá trị trước khi tạo settings.

## Bằng chứng

- Red test trước implementation: **2 failed**, đúng vì direct construction chưa
  từ chối path không canonical.
- Targeted sau implementation:
  `uv run pytest -q tests/test_phase_1_settings.py -k
  'non_canonical_path_whitespace or canonical_text or
  settings_construction_rejects_non_canonical_text'` → **7 passed**.
- Full offline suite: `uv run pytest -q` → **810 passed, 3 skipped, 1
  warning**; `compileall` và `git diff --check` đều đạt.
- Live model-service smoke và production golden parity vẫn cần endpoint,
  credential và catalog production thật nên chưa thể xác minh trong checkout
  này.
