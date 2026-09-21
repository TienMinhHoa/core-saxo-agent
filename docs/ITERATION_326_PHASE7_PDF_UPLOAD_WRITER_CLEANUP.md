# Iteration 326 — Dọn helper ghi upload PDF chết

## Phạm vi

Sau Iteration 325, route `POST /api/jobs` đã chuyển việc ghi upload sang
`PdfLayoutJobStore.save_uploaded_pdf()` và chạy I/O qua `asyncio.to_thread`.
Helper `_save_upload()` trong HTTP interface không còn caller, nên tiếp tục giữ
helper này sẽ làm trùng ownership persistence tại route.

## Thay đổi

- Loại bỏ helper `_save_upload()` khỏi `saxophone.interfaces.pdf_layout_web`.
- Thêm contract test bảo đảm interface không đọc upload trực tiếp bằng
  `await upload.read(...)` và vẫn ủy quyền cho `JOB_STORE.save_uploaded_pdf`.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py --basetemp=.pytest-tmp -q`
  — **20 passed**.
- Cần chạy lại full offline suite sau khi hoàn tất các slice Phase 7 liên quan.
- Live model-service smoke và production parity chưa xác minh vì checkout chưa có
  endpoint, credential và production catalog thật.

## Kết luận

Slice này củng cố nguyên tắc Clean Code của Phase 7: HTTP interface chỉ điều
phối; policy ghi artifact và giới hạn dung lượng thuộc job store.
