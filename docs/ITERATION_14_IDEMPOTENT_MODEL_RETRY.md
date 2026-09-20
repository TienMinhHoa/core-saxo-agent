# Iteration 14 — Retry model request có idempotency key

## Phạm vi

Lát cắt này đóng một khoảng trống trong tiêu chí 20 và mục 12.5 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: retry ở model boundary chỉ được mở
cho request có khóa idempotency, để một lần gọi lại không tạo ra tác dụng phụ
ngoài ý muốn.

## Thay đổi

- Bổ sung `ModelRequest.idempotency_key`, validate và chuẩn hóa giá trị ở
  boundary.
- `LiteLLMModelClient` gửi header `Idempotency-Key` và chỉ dùng
  `max_attempts` khi request có khóa; request không có khóa chỉ chạy một lần.
- Extraction dùng `correlation_id` làm khóa; embedding dùng digest ổn định của
  source/chunk; tagging, conflict resolution và answer generation đều tạo khóa
  ổn định từ input nghiệp vụ.
- Bổ sung regression tests cho header, validation và việc không retry request
  không có khóa.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_litellm_client.py tests/test_phase_1_model_client_contract.py tests/test_phase_3_remote_pdf_extractor.py tests/test_phase_4_remote_embedding_provider.py tests/test_phase_8_remote_tagging.py tests/test_remote_answer_generator.py
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Kết quả thực tế:

```text
uv run pytest -q: 293 passed, 2 skipped, 1 warning
compileall: passed
git diff --check: passed
```

Đây là bằng chứng offline; live model-service smoke vẫn chưa thể xác minh vì
checkout không có endpoint và credential thật.

## Giới hạn

Lát cắt này không tuyên bố production parity hoặc tính đúng đắn của chính sách
idempotency phía provider. Provider thật cần được kiểm tra rằng họ tôn trọng
header này khi live smoke được cấp endpoint và credential.
