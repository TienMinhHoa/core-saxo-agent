# Bằng chứng Iteration 255 — inbound boundary của tagging

## Phạm vi

Khóa quy tắc dependency của Phase 7 cho package `saxophone.tagging`: application
code không được import trực tiếp FastAPI, Pydantic hoặc module inbound
`saxophone.interfaces`. Tagging chỉ nhận contract/port; HTTP schema và route nằm ở
lớp ngoài.

## Thay đổi

- Bổ sung test AST `test_tagging_does_not_depend_on_inbound_framework_or_schemas`.
- Test quét toàn bộ file Python trong `src/saxophone/tagging`, kiểm tra import root
  `fastapi`/`pydantic` và import nội bộ bắt đầu bằng `saxophone.interfaces`.
- Không cần sửa production code vì tagging hiện đã tuân thủ boundary.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_dependency_enforcement.py -q
17 passed
```

## Kết luận và giới hạn

Inbound boundary của tagging đã có enforcement offline. Đây không phải bằng chứng
cho live model-service smoke hoặc production parity; hai kiểm tra đó vẫn cần
endpoint, credential và catalog production thật.
