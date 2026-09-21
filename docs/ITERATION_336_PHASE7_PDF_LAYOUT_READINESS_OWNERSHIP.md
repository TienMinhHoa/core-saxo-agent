# Iteration 336 - ownership policy sẵn sàng của layout PDF

## Phạm vi

Theo hướng Clean Code trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, iteration
này thu hẹp một slice: persistence boundary phải sở hữu policy xác định khi
layout PDF đã sẵn sàng; HTTP route chỉ điều phối và ánh xạ lỗi sang HTTP.

## Thay đổi

- Thêm `PdfLayoutJobStore.load_completed_state()` để đọc state và từ chối mọi
  trạng thái khác `completed` bằng lỗi typed ở boundary.
- Route `GET /api/jobs/{job_id}/layout` gọi facade trên, không còn tự kiểm tra
  `state["status"]` hoặc sở hữu helper load-state riêng.
- Giữ mapping HTTP rõ ràng: job không tồn tại là 404, layout chưa sẵn sàng là
  409.
- Bổ sung contract tests cho store, route delegation và missing-job mapping.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py -q` -> **67 passed**.
- `uv run python -m compileall -q src` -> đạt.
- `git diff --check` -> đạt; chỉ còn cảnh báo newline CRLF chuẩn của checkout Windows.
- Chưa chạy live model-service smoke hoặc production golden parity vì checkout
  vẫn không có endpoint, credential và catalog production được phê duyệt.
