# Iteration 320 — ownership state workflow PDF

## Phạm vi

Iteration này hoàn tất một lát cắt nhỏ của Phase 7 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: workflow OCR PDF không còn tự nhận
callback `load_state`/`write_state` để đọc, sửa rồi ghi state. `PdfLayoutJobStore`
là boundary duy nhất áp dụng patch state và persist atomically.

## Thay đổi

- Thêm `PdfLayoutJobStore.update_state(job_id, updates)` để load state hiện tại,
  áp dụng patch và ghi qua cơ chế file tạm + replace hiện có.
- `run_extraction()` chỉ dùng callback `update_state` và typed artifact-path
  policy; không còn biết chi tiết load/write persistence.
- Route PDF truyền `JOB_STORE.update_state`; đã loại bỏ `_write_state` và
  callback `load_state` khỏi workflow wiring.
- Thêm contract test cho state patch, persistence và AST boundary của workflow.

## Bằng chứng kiểm tra

- Targeted PDF contracts: `31 passed`.
- Full offline suite: `1016 passed, 18 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo line ending CRLF chuẩn của checkout.
- Không chạy live model-service smoke vì checkout vẫn thiếu endpoint, credential
  và production catalog thật.

## Kết luận lát cắt

Đạt mục tiêu cục bộ: persistence state transition của PDF workflow đã được gom
về job store, còn HTTP interface chỉ điều phối. Stop condition toàn bộ vẫn chưa
đạt vì live smoke/production parity và các phần cleanup Phase 7 khác chưa được
xác minh đầy đủ.
