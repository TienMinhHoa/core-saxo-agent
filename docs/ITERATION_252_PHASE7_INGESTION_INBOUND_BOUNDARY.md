# Iteration 252 — Khóa inbound boundary của ingestion

## Phạm vi

Tiếp tục Phase 7 trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, cụ thể
rule 6 của mục Dependency enforcement: module `ingestion` không được biết
FastAPI, Pydantic hay inbound HTTP interface. Ingestion là application/domain
capability và chỉ nhận command/port nội bộ.

## Thay đổi

- Bổ sung test AST `test_ingestion_does_not_depend_on_inbound_framework_or_schemas`
  trong `tests/test_phase_7_dependency_enforcement.py`.
- Guard quét toàn bộ `src/saxophone/ingestion/**/*.py`, chặn import gốc
  `fastapi`, `pydantic` và mọi import `saxophone.interfaces`.
- Không thay đổi runtime behavior hay public API; enforcement chỉ ngăn vi phạm
  kiến trúc quay trở lại.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q` — **14 passed**.
- Full suite: `uv run pytest -q` — **935 passed, 18 skipped, 1 warning** trong
  41.33 giây.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; Git chỉ cảnh báo quy đổi LF/CRLF trên Windows.
- Live model-service smoke và production parity vẫn chưa xác minh được vì
  checkout không có endpoint, credential và production catalog thật.

## Kết luận

Inbound framework đã được giữ ở lớp `interfaces`; ingestion tiếp tục phụ thuộc
contract nội bộ thay vì schema/router HTTP. Đây là một enforcement nhỏ, độc lập
và phù hợp với hướng Clean Code của kế hoạch.
