# Iteration 313 — ranh giới tạo job PDF

## Mục tiêu

Tiếp tục Phase 7 bằng cách chuyển policy tạo thư mục và state ban đầu của PDF job
ra khỏi HTTP interface. Route chỉ còn nhận upload, gọi job store và trả projection
an toàn cho trình duyệt.

## Thay đổi

- Thêm `PdfLayoutJobStore.create_uploaded_job()` để sở hữu việc tạo UUID-backed
  directory và state `uploaded` đầy đủ.
- State được ghi qua `write_state()` và directory được dọn nếu ghi state thất bại.
- `create_job()` trong `pdf_layout_web.py` không còn tự dựng state fields; nó gọi
  job store rồi dùng `public_state()`.
- Bổ sung contract test bảo vệ delegation và test store cho happy path/collision.

## Bằng chứng

- Targeted: `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q`
  — **19 passed**.
- Cần chạy full suite sau khi hoàn tất slice tiếp theo; iteration này chưa tuyên bố
  production/live model-service smoke.
- Live model-service smoke và production parity vẫn bị chặn bởi checkout thiếu
  endpoint, credential và production catalog.

## Quyết định Clean Code

Persistence policy thuộc job store; HTTP adapter không nên biết danh sách state
fields hay tự quản lý invariant khởi tạo job.
