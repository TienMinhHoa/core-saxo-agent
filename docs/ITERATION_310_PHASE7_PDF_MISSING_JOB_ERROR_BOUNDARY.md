# Iteration 310 — boundary lỗi job PDF không tồn tại

## Phạm vi

Hoàn thiện một đơn vị nhỏ của Phase 7: đường dẫn HTTP của PDF layout phải
chuyển lỗi `PdfLayoutJobNotFound` từ store thành HTTP 404 ổn định.

## Thay đổi

- Bổ sung import `PdfLayoutJobNotFound` vào
  `src/saxophone/interfaces/pdf_layout_web.py`.
- Giữ nguyên chính sách của interface: job không tồn tại được báo 404; các lỗi
  đọc state còn lại vẫn đi qua nhánh lỗi hiện có.
- Thêm regression test trong
  `tests/test_phase_7_pdf_layout_wrapper.py` để gọi `_load_state()` với store
  giả lập ném `PdfLayoutJobNotFound` và kiểm tra `HTTPException.status_code == 404`.

## Bằng chứng

- Trước thay đổi, test mới tái hiện lỗi `NameError: name
  'PdfLayoutJobNotFound' is not defined` ngay trong mệnh đề `except`.
- Sau thay đổi: test mục tiêu **1 passed**.
- Full suite: **999 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo quy đổi LF/CRLF chuẩn của Git trên
  Windows.

## Giới hạn xác minh

Chưa thực hiện live model-service smoke hoặc production parity vì checkout hiện
không có endpoint, credential và production catalog thật. Không có background
process nào được khởi chạy trong iteration này.
