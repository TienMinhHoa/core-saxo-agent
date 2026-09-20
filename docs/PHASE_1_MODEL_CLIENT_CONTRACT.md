# Phase 1 - Hợp đồng model client dùng chung

## Phạm vi lát cắt

Đã bổ sung cổng async `ModelClient` cùng `ModelRequest` và `ModelResponse` để
use case không phụ thuộc LiteLLM, HTTP client hay SDK của nhà cung cấp. Hợp đồng
bao phủ các `task` đã nêu trong solution architecture và giữ `model`, schema,
metadata, output cùng `source_version` ở dạng typed DTO.

## Bằng chứng

- `tests/test_phase_1_model_client_contract.py` kiểm tra task hợp lệ, payload
  bất biến, provenance/schema bắt buộc, input sai và lời gọi async qua fake.
- Validation offline: targeted `uv run pytest tests/test_phase_1_model_client_contract.py`
  đạt `6 passed`; toàn bộ `uv run pytest` đạt `120 passed, 2 skipped, 1 warning`.
- `python -m compileall -q src tests` và `git diff --check` đều đạt.

## Ranh giới còn lại

Lát cắt này chưa triển khai HTTP/LiteLLM adapter, retry hoặc mapping response
provider. Các phần đó sẽ dùng `ModelClient` làm port ở lát cắt kế tiếp; không
đưa SDK model vào domain/application.
