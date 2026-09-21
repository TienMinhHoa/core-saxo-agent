# Iteration 257 — public facade cho retrieval

## Phạm vi

Iteration này xử lý một đơn vị nhỏ của Phase 7 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: module `chat` chỉ được phụ
thuộc retrieval qua public facade/port, không ghép trực tiếp vào module triển
khai use case hoặc port nội bộ.

## Thay đổi

- `saxophone.retrieval` export các contract và use case công khai:
  `ChunkHit`, `EvidenceBundle`, `ChunkRetriever` và `RetrieveEvidence`.
- `chat.service` và `chat.ports` import từ `saxophone.retrieval` thay vì
  `saxophone.retrieval.use_cases` hoặc `saxophone.retrieval.models`.
- Thêm AST contract test bảo đảm `chat.service` dùng facade và không import
  trực tiếp `retrieval.use_cases`/`retrieval.ports`.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **18 passed**.
- `uv run pytest -q`: **939 passed, 18 skipped, 1 warning**.
- `git diff --check`: đạt.

## Trạng thái còn lại

Đây là kiểm tra offline/static. Live model-service smoke và production golden
parity chưa được xác minh vì checkout hiện không có endpoint, credential và
production catalog thật.
