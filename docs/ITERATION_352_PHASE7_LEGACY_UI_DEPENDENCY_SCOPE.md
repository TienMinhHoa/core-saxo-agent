# Iteration 352 - khoá phạm vi dependency UI legacy

## Mục tiêu

Tiêu chí Phase 7 yêu cầu backend runtime không kéo theo UI legacy. Slice này
khóa rõ Gradio chỉ là dependency tùy chọn của compatibility UI, không phải
dependency runtime của `saxophone-api`.

## Thay đổi

- Bổ sung contract test `test_legacy_ui_dependency_is_optional_and_not_runtime`.
- Test đọc metadata `pyproject.toml`, xác nhận `gradio` vắng trong runtime
  dependencies và có mặt trong nhóm tùy chọn `legacy-ui`.

## Bằng chứng

- Targeted contract: `uv run pytest -q tests/test_phase_7_dependency_enforcement.py`.
- Targeted contract đạt **47 passed**; full suite đạt **1066 passed, 18
  skipped, 1 warning**. `compileall` và `git diff --check` đều đạt.
- Live model-service smoke vẫn chưa chạy vì checkout không có endpoint,
  credential và production catalog thật.
