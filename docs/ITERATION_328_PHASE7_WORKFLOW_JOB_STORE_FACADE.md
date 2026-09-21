# Iteration 328 - Facade public cho PDF job store

## Phạm vi

Sau Iteration 327, HTTP adapter PDF vẫn import trực tiếp module triển khai
`saxophone.workflows.pdf_layout_jobs`. Slice này đưa contract job store qua
facade public `saxophone.workflows`, phù hợp quy tắc Phase 7 về dependency
boundary và giữ implementation module ở phía sau facade.

## Thay đổi

- Export `PdfLayoutJobStore` và `PdfLayoutJobNotFound` từ
  `saxophone.workflows.__init__`.
- Đổi PDF HTTP interface sang import hai symbol qua `saxophone.workflows`;
  không còn phụ thuộc trực tiếp `pdf_layout_jobs`.
- Thêm contract test bảo vệ public export và cấm import implementation trực
  tiếp trong interface.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py tests/test_phase_7_pdf_layout_wrapper.py tests/test_pdf_layout_job_store.py -q` — **81 passed**.
- Full offline: `uv run pytest -q` — **1026 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; Git chỉ cảnh báo chuyển line ending LF sang CRLF.
- Live model-service smoke và production parity chưa xác minh vì checkout vẫn thiếu endpoint, credential và production catalog thật.

## Kết luận

Slice hoàn tất một bước enforcement nhỏ của Phase 7: HTTP adapter chỉ biết facade workflow ổn định, còn policy job store vẫn thuộc module triển khai.
