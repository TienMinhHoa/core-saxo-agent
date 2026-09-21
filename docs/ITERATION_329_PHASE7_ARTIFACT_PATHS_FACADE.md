# Iteration 329 — facade public cho policy artifact PDF

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: sau khi
`PdfLayoutJobStore` đã đi qua `saxophone.workflows`, DTO
`PdfLayoutArtifactPaths` cũng phải đi qua cùng public facade. Workflow không
nên phụ thuộc trực tiếp vào module triển khai `pdf_layout_jobs`.

## Thay đổi

- Export `PdfLayoutArtifactPaths` từ `saxophone.workflows`.
- Đổi `pdf_layout_extraction.py` sang import DTO qua public facade.
- Giữ thứ tự import facade an toàn để tránh vòng lặp: job-store contracts được
  nạp trước workflow implementation.
- Bổ sung contract test bảo vệ export duy nhất và cấm import private module.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q`: **24 passed**.
- `uv run pytest -q`: **1028 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển đổi newline CRLF tự nhiên
  của Git trên Windows.
- Live model-service smoke/production parity vẫn chưa xác minh vì checkout
  không có endpoint, credential và production catalog thật.
