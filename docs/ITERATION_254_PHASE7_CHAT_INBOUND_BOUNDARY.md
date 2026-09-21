# Bằng chứng Iteration 254 — boundary inbound của chat

## Phạm vi

Khóa quy tắc dependency của Phase 7 cho package `saxophone.chat`: application
code không được import trực tiếp FastAPI, Pydantic hoặc module inbound
`saxophone.interfaces`. Chat chỉ nhận application contract/port; HTTP schema và
route nằm ở lớp ngoài.

## Thay đổi

- Bổ sung test AST `test_chat_does_not_depend_on_inbound_framework_or_schemas`.
- Test quét toàn bộ file Python trong `src/saxophone/chat`, bắt cả import root
  `fastapi`/`pydantic` và import nội bộ bắt đầu bằng `saxophone.interfaces`.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_dependency_enforcement.py -q
16 passed
```

## Kết luận và giới hạn

Inbound boundary của chat đã có enforcement offline. Đây không phải bằng chứng
cho live model-service smoke hoặc production parity; hai kiểm thử đó vẫn cần
endpoint, credential và catalog production thật.
