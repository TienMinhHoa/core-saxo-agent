# Bằng chứng Iteration 253 — boundary inbound của extraction

## Phạm vi

Khóa một quy tắc dependency nhỏ của Phase 7: package `saxophone.extraction`
không được import trực tiếp FastAPI, Pydantic hoặc module inbound
`saxophone.interfaces`. Extraction chỉ nhận contract/application dependency;
HTTP schema và route nằm ở lớp ngoài.

## Thay đổi

- Bổ sung test AST `test_extraction_does_not_depend_on_inbound_framework_or_schemas`.
- Test quét toàn bộ file Python trong `src/saxophone/extraction`, bắt cả import
  root `fastapi`/`pydantic` và import nội bộ bắt đầu bằng
  `saxophone.interfaces`.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_dependency_enforcement.py -q
15 passed in 0.89s
```

## Kết luận và giới hạn

Rule inbound boundary của extraction đạt ở mức kiểm tra tĩnh offline. Đây
không phải bằng chứng cho live model-service smoke hoặc production parity;
hai kiểm tra đó vẫn cần endpoint, credential và catalog production thật.

