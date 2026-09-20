# Phase 1 — Kiểm tra identity của response LiteLLM

## Phạm vi

Lát cắt này củng cố contract của `LiteLLMModelClient`: response từ model service
chỉ được chấp nhận khi giữ nguyên ba định danh của request:

- `task_type` phải trùng `ModelRequest.task`;
- `model` phải trùng profile model đã gửi;
- `response_format` phải trùng schema đã yêu cầu.

Mục tiêu là không để output hợp lệ về mặt hình dạng nhưng đến từ task, model hoặc
schema khác bị chuyển tiếp vào application use case.

## Thay đổi

- Thêm test contract parameterized cho cả ba trường hợp mismatch.
- Thêm validation ngay sau khi parse response envelope, trước khi tạo
  `ModelResponse`.
- Giữ nguyên retry policy: chỉ retry lỗi transport/HTTP transient; mismatch là
  lỗi contract và không retry.

## Bằng chứng kiểm tra

```text
uv run pytest -q tests/test_phase_1_litellm_client.py
8 passed

uv run pytest -q
247 passed, 2 skipped, 1 warning

python -m compileall -q src tests
pass

git diff --check
pass
```

Hai test skip là do môi trường checkout thiếu Gradio và sample source; không liên
quan đến lát cắt này.

## Giới hạn còn lại

Validation này chỉ xác nhận identity của envelope. Việc kiểm tra schema chi tiết
của `output` vẫn thuộc adapter task-specific (`RemotePdfExtractor`, embedding,
tagging hoặc answer generator), không nên nhồi vào transport client dùng chung.
