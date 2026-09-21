# Iteration 272 — tách port vector khỏi facade `documents`

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: facade công khai
của `documents` chỉ giữ contract thuộc document/persistence. `VectorIndex` đã
được định nghĩa và sử dụng trong `ingestion`, nên không nên xuất hiện thêm ở
`documents` hoặc kéo ngược `saxophone.ingestion.models` vào document ports.

## Thay đổi

- Xóa `VectorIndex` khỏi `saxophone.documents.ports` và facade
  `saxophone.documents`.
- Xóa import `EmbeddingRecord` từ `ingestion.models` khỏi document ports; port
  vector chính thức vẫn là `saxophone.ingestion.ports.VectorIndex`.
- Thêm contract test xác nhận facade `documents` không re-export `VectorIndex`.

## Bằng chứng

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py`
- Full suite: `958 passed, 18 skipped, 1 warning`.
- Static: `python -m compileall -q src tests` và `git diff --check`.

## Ranh giới còn lại

Đây là kiểm chứng offline/static. Live model-service, production catalog và
golden parity vẫn chưa thể chạy vì checkout chưa có endpoint, credential và dữ
liệu production được cấp quyền.
