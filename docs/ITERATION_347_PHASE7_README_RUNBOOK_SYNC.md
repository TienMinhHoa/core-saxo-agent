# Iteration 347 - đồng bộ README/runbook Phase 7

## Phạm vi

Đồng bộ hướng dẫn vận hành với exit criteria Phase 7 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: chỉ quảng bá web entrypoint
`saxophone-api`, và nói rõ OCR/VLM/Paddle/CUDA thuộc model service hoặc tooling
legacy, không thuộc runtime backend.

## Thay đổi

- Đổi lệnh khởi động PDF viewer trong README từ `pdf-layout-web` sang
  `saxophone-api`.
- Ghi rõ backend không tự chạy GPU local; tham số `device` chỉ là profile tương
  thích của workflow.

## Bằng chứng

- `pyproject.toml` chỉ công bố console script `saxophone-api` cho web backend;
  test Phase 7 cũng kiểm tra không còn script `pdf-layout-web`.
- `src/pdf_layout_web.py` chỉ còn compatibility wrapper, không chứa route hoặc
  orchestration business logic.
- Kiểm tra văn bản sau chỉnh sửa: README không còn lệnh `uv run pdf-layout-web`.

## Kiểm tra

- `uv run pytest tests/test_phase_7_backend_entrypoint.py tests/test_phase_7_dependency_enforcement.py tests/test_phase_7_pdf_layout_wrapper.py`
- `uv run python -m compileall -q src`
- `git diff --check`

Live model-service smoke và production parity chưa thực hiện vì checkout không
có endpoint, credential và production catalog thật.
