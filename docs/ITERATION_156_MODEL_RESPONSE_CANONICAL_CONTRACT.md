# Bằng chứng Iteration 156 — canonical contract của `ModelResponse`

## Phạm vi

Siết boundary dùng chung cho model-service: `ModelResponse` không được âm thầm
chuẩn hóa metadata bằng `.strip()`, vì việc đó có thể che khuất response drift
trước khi adapter kiểm tra identity và provenance.

## Thay đổi

- `model`, `response_schema` và `source_version` phải là chuỗi canonical:
  không rỗng, không có whitespace đầu/cuối, không có ASCII control/DEL và đã
  ở dạng Unicode NFC.
- Response vi phạm bị từ chối bằng `ModelValidationError`; không có fallback
  hoặc sửa ngầm dữ liệu từ provider.
- Bổ sung 9 regression cases bao phủ cả ba field và ba dạng dữ liệu không hợp
  lệ.

## Kiểm chứng

- `uv run pytest tests/test_phase_1_model_client_contract.py tests/test_phase_3_remote_pdf_extractor.py tests/test_phase_4_remote_embedding_provider.py tests/test_phase_8_remote_tagging.py tests/test_remote_answer_generator.py -q --basetemp=.pytest-tmp`
  → **47 passed**.
- Full suite `uv run pytest -q --basetemp=.pytest-tmp` đạt **681 passed, 3
  skipped, 1 warning**.
- `python -m compileall -q src tests` và `git diff --check` đều đạt.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout chưa có endpoint, credential và catalog production thật.
