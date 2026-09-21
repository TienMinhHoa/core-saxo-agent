# Iteration 309 — giới hạn shape của persisted PDF job state

## Mục tiêu

Tiếp tục Phase 7 theo `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: policy
persistence phải validate dữ liệu trước khi state được dùng bởi interface. Một
file `job.json` có cú pháp JSON hợp lệ nhưng là list hoặc scalar không phải là
browser-facing job state hợp lệ.

## Thay đổi

- `PdfLayoutJobStore.load_state()` chỉ chấp nhận JSON object (`dict`).
- JSON đúng cú pháp nhưng sai shape được chuyển thành `PdfLayoutJobNotFound`,
  cùng contract với state bị thiếu/hỏng, thay vì để route lỗi muộn khi gọi
  `.get()` trên kiểu dữ liệu không phù hợp.
- Thêm regression test cho `job.json` chứa JSON list.

## Bằng chứng kiểm thử

- `uv run pytest -q tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py`
  → **13 passed**.
- `python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt.
- Full suite chưa chạy trong iteration này.

## Trạng thái còn lại

Live model-service smoke và production parity chưa xác minh vì checkout vẫn
thiếu endpoint, credential và production catalog thật. Thay đổi này chỉ củng
cố offline persistence boundary, không giả định đã chứng minh live behavior.
