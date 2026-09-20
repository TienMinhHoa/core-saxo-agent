# Phase 1 - Chuẩn hóa lỗi JSON response từ model service

## Phạm vi

`LiteLLMModelClient` là boundary chung của các task OCR, embedding, tagging và
answer. Khi upstream trả HTTP 200 nhưng body không phải JSON hợp lệ, boundary
phải trả lỗi domain `ModelValidationError`; application không nên phụ thuộc vào
loại exception parser riêng của HTTP client.

## Thay đổi

- Bọc `response.json()` trong `try/except ValueError`.
- Chuyển JSON hỏng thành `ModelValidationError("model response JSON is invalid")`.
- Giữ nguyên contract hiện có cho HTTP status lỗi và response JSON hợp lệ nhưng
  sai schema.

## Bằng chứng

- Test mới kiểm tra HTTP 200 với body không phải JSON và xác nhận lỗi boundary.
- Targeted test: `uv run pytest -q tests/test_phase_1_litellm_client.py`.
- Full suite và `compileall` được chạy ở cuối iteration.

## Giới hạn xác minh

Chưa có live model service trong checkout để smoke test; bằng chứng hiện tại là
contract test offline với `httpx.MockTransport`.
