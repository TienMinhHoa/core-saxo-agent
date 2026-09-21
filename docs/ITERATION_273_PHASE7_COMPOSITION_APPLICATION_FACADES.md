# Iteration 273 - composition root dùng facade application

## Phạm vi

Đã hoàn tất một lát cắt nhỏ của Phase 7 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: composition root phải wiring qua
public facade ổn định, không để `saxophone.app.factory` phụ thuộc trực tiếp vào
các module implementation của extraction, ingestion và tagging.

## Thay đổi

- Chuyển import contract/use case extraction trong `saxophone.app.factory` sang
  `saxophone.extraction`.
- Chuyển `IndexDocument`/`IngestDocument` và các contract ingestion sang
  `saxophone.ingestion`; bổ sung lazy export `IngestDocument` vào facade.
- Chuyển contract, adapter và use case tagging mà composition root cần dùng sang
  `saxophone.tagging`.
- Bổ sung AST enforcement test để import implementation trực tiếp trong factory
  không quay trở lại.

## Bằng chứng kiểm chứng

```text
uv run pytest tests/test_phase_1_composition_root.py tests/test_phase_7_api_routes.py tests/test_phase_7_dependency_enforcement.py -q
110 passed, 1 warning

uv run pytest -q
959 passed, 18 skipped, 1 warning

uv run python -m compileall -q src tests
OK

git diff --check
OK (chỉ cảnh báo chuyển LF/CRLF của Git trên Windows)
```

## Trạng thái còn lại

Offline suite và dependency boundary vẫn xanh. Live model-service smoke và
production golden parity chưa thể xác minh trong checkout này vì chưa có
endpoint, credential và production catalog được cấp; đây vẫn là blocker ngoại
vi code change của iteration này.
