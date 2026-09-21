# Iteration 333 - ownership trạng thái queue của PDF job

## Phạm vi

Route `POST /api/jobs/{job_id}/extract` trước đây tự đọc `status` của job để
quyết định có cho queue hay không. Điều này tạo hai nơi sở hữu cùng một policy:
HTTP interface và `PdfLayoutJobStore.queue_extraction()`.

## Thay đổi

- Loại bỏ kiểm tra `state.get("status")` khỏi HTTP route.
- Để `PdfLayoutJobStore.queue_extraction()` là nơi duy nhất kiểm tra trạng thái
  hợp lệ (`uploaded` hoặc `failed`) và ghi state `queued`.
- Giữ nguyên mapping `ValueError` từ store thành HTTP 409 tại interface.
- Bổ sung contract test bảo vệ route không tái tạo policy status và regression
  test cho queue conflict.

## Bằng chứng xác minh

- `uv run pytest -q tests/test_phase_7_pdf_layout_wrapper.py`: **28 passed**.
- `python -m compileall -q src`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo chuyển LF sang CRLF của Git trên
  Windows.
- `uv run pytest -q`: **1037 passed, 18 skipped, 1 warning**. Các skip chủ yếu
  do quyền symbolic link trên Windows, Gradio chưa cài hoặc thiếu sample source.
- Không có live model-service smoke vì checkout vẫn thiếu endpoint, credential và
  production catalog thật.

## Kết luận Clean Code

Một policy chuyển trạng thái chỉ còn thuộc persistence/workflow boundary; route
chỉ chuẩn hóa input, gọi use case/store và chuyển lỗi sang giao thức HTTP.
