# Iteration 322 — tiêu thụ policy đường dẫn PDF dạng typed DTO

## Phạm vi

Iteration này xử lý một lát cắt nhỏ còn lại của Phase 7: sau khi
`PdfLayoutJobStore` đã sở hữu policy artifact, HTTP interface không nên gọi
từng accessor đường dẫn riêng lẻ cho upload, layout và page image.

## Thay đổi

- Mở rộng `PdfLayoutArtifactPaths` với trường `layout`.
- `PdfLayoutJobStore.artifact_paths()` trả về đủ bốn đường dẫn canonical:
  `source_pdf`, `extraction`, `pages`, `layout`.
- Upload, layout route và page-image route chỉ tiêu thụ DTO typed này; cấu trúc
  thư mục không còn bị lặp lại ở nhiều accessor trong interface.
- Bổ sung contract test để khóa mapping DTO và ngăn HTTP interface quay lại
  gọi `source_pdf_path()`, `pages_dir()` hoặc `layout_dir()` trực tiếp.

## Bằng chứng kiểm tra

- `uv run pytest -q tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py`
  — **32 passed**.
- `git diff --check` — đạt; chỉ còn cảnh báo line-ending CRLF chuẩn của
  checkout Windows.

## Trạng thái còn lại

Lát cắt offline này đã hoàn tất. Live model-service smoke và production parity
chưa thể xác minh vì checkout vẫn thiếu endpoint, credential và catalog
production thực tế; đây là blocker môi trường, không phải lỗi của thay đổi này.
