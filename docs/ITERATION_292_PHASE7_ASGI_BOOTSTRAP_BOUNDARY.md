# Iteration 292 - Khóa ranh giới ASGI bootstrap Phase 7

## Thay đổi

Thêm contract test `test_backend_asgi_module_is_only_a_bootstrap_boundary`.
Test yêu cầu `src/saxophone/main.py` chỉ import hai module nội bộ cần thiết cho
bootstrap: `saxophone.app.factory` và `saxophone.app.settings`. Route, concrete
adapter và provider wiring vì vậy tiếp tục thuộc composition root, không bị kéo
vào ASGI entrypoint.

## Bằng chứng

- `uv run pytest -q tests/test_phase_7_dependency_enforcement.py -k
  "asgi_module_is_only_a_bootstrap_boundary or
  project_declares_one_backend_asgi_entrypoint" --basetemp=.pytest-tmp-292-bootstrap`
  -> **2 passed, 39 deselected**.
- Đây là kiểm tra source-level/offline; chưa phải live smoke model-service.

## Trạng thái

Slice này củng cố tiêu chí Phase 7 về một ASGI entrypoint và composition root
riêng biệt. Live model-service smoke và production golden parity vẫn chờ
endpoint, credential và catalog production được cung cấp.
