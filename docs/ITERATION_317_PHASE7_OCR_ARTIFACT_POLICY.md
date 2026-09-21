# Bằng chứng Iteration 317 — policy artifact cho workflow OCR PDF

## Phạm vi

Iteration này xử lý một seam còn sót lại của Phase 7: workflow OCR trước đây
nhận callback tổng quát `job_dir` rồi tự ghép `source.pdf`, `extraction` và
`pages`. Cách đó khiến workflow vẫn biết cấu trúc thư mục persistence của
interface.

## Thay đổi

- `PdfLayoutJobStore` sở hữu policy `source_pdf_path()`, `extraction_dir()` và
  `pages_dir()`.
- `run_extraction()` chỉ nhận ba policy path tường minh và không còn nhận
  `job_dir`.
- Route `start_extraction()` truyền trực tiếp các policy từ `JOB_STORE`, còn
  workflow không tự ghép đường dẫn job.
- Bổ sung contract test bảo vệ API callback mới và mapping artifact path.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py tests/test_pdf_layout_job_store.py --basetemp=.pytest-tmp`
- Kết quả targeted: **25 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp` → **1010 passed, 18 skipped, 1 warning**.
- Syntax: `uv run python -m compileall -q src tests` → đạt.
- Hygiene: `git diff --check` → đạt.
- Live model-service smoke và production parity vẫn chưa xác minh được vì
  checkout không có endpoint, credential và catalog production thật.

## Trạng thái

Slice này hoàn tất phần tách policy artifact của workflow OCR. Các phần runtime
phụ thuộc model service vẫn cần live smoke riêng khi môi trường được cấp đủ.
