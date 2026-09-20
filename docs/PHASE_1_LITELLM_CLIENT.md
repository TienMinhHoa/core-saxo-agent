# Phase 1 - LiteLLM model client

## Phạm vi

Đã triển khai adapter `LiteLLMModelClient` ở tầng `platform`. Adapter nhận
`ModelRequest` typed, gửi request/response trực tiếp qua một `httpx.AsyncClient`
được inject từ composition root, và chuyển response về `ModelResponse` sau khi
kiểm tra task, schema, output và source version. Adapter không tạo job ID, không
poll trạng thái và không biết provider SDK.

Envelope gửi đi dùng các trường `model`, `task_type`, `input`, `metadata` và
`response_format` theo mục 12.5 của solution architecture. Endpoint và bearer
token được truyền vào constructor; task-specific adapter tiếp tục chịu trách
nhiệm kiểm tra business output.

## Bằng chứng

- `tests/test_phase_1_litellm_client.py`: 3 contract tests cho mapping envelope,
  authentication, response validation và HTTP failure.
- `uv run pytest tests/test_phase_1_litellm_client.py tests/test_phase_1_model_client_contract.py tests/test_remote_answer_generator.py`: **12 passed**.
- `uv run pytest`: **126 passed, 2 skipped, 1 warning**. Hai test skip là do
  Gradio và sample source không có trong checkout, không phải regression của
  lát cắt này.
- `python -m compileall -q src tests` và `git diff --check`: đạt.

## Ranh giới còn lại

Lát cắt này chưa nối client vào `AppContainer` và chưa chọn model endpoint từ
environment; việc đó cần một lát cắt composition-root riêng để bổ sung config,
lifecycle shutdown và override test mà không làm lẫn transport với use case.
