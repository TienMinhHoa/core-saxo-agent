# Iteration 319 — ownership cleanup job PDF upload lỗi

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: persistence
boundary phải sở hữu policy và vòng đời artifact của PDF job. Slice này chỉ xử
lý cleanup khi upload thất bại giữa chừng.

## Thay đổi

- Thêm `PdfLayoutJobStore.discard_job(job_id)` để xóa job directory và artifact
  dở dang sau lỗi upload.
- Route `POST /api/jobs` chỉ gọi `JOB_STORE.discard_job(job_id)` trong nhánh
  cleanup; interface không còn trực tiếp gọi `shutil.rmtree`.
- Thêm contract test chứng minh store xóa partial upload và route không sở hữu
  cleanup filesystem.

## Bằng chứng

- `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q`
  — **29 passed**.
- Chưa chạy live model-service smoke hoặc production parity: checkout vẫn thiếu
  endpoint, credential và production catalog thật.
- Không khởi động background process.

## Kết luận

Slice cleanup ownership đạt yêu cầu offline. Phase 7 vẫn chưa thể đóng hoàn
toàn vì live smoke/production parity còn bị chặn bởi môi trường triển khai.
