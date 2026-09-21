# Iteration 316 — policy đường dẫn artifact PDF

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: boundary HTTP
không tự biết cấu trúc thư mục artifact của một PDF job.

## Thay đổi

- `PdfLayoutJobStore` sở hữu ba policy path có tên rõ ràng:
  `source_pdf_path()`, `pages_dir()` và `layout_dir()`.
- Route PDF dùng các policy này khi lưu upload, đọc layout và phục vụ ảnh
  trang; không còn tự ghép `source.pdf`, `pages` hay
  `extraction/source/layout`.
- Contract test bảo vệ cả giá trị path của store và việc route không quay lại
  hard-code cấu trúc thư mục.

## Bằng chứng kiểm chứng

- Test targeted: `24 passed`.
- `python -m compileall -q src`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo line ending LF/CRLF của Git.
- Chưa chạy live model-service smoke vì checkout vẫn thiếu endpoint, credential
  và production catalog thật.

## Giới hạn còn lại

Workflow OCR vẫn nhận callback `job_dir` để tương thích adapter cũ; việc gom
toàn bộ artifact access của workflow về store là một bước riêng, cần giữ
contract với pipeline legacy.
