# Iteration 263 — Public facade cho `documents`

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: consumer không
được phụ thuộc trực tiếp vào implementation module của `documents`; các
contract, policy và port phải đi qua một public facade ổn định.

## Thay đổi

- Mở rộng `saxophone.documents` để export `ArtifactRef`, `ArtifactKind`,
  `KnowledgeChunk`, các repository/index port và policy kiểm tra reference.
- Dùng lazy export trong facade để tránh vòng import giữa `documents.ports` và
  `ingestion.models`.
- Chuyển app factory, chat, extraction, ingestion, API, platform và workflows
  sang import từ `saxophone.documents`.
- Bổ sung AST contract test cấm consumer import trực tiếp
  `documents.knowledge`, `documents.models`, `documents.policies` hoặc
  `documents.ports`, đồng thời kiểm tra đầy đủ public exports.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **26 passed**.
- `git diff --check`: đạt; cảnh báo còn lại chỉ là quy đổi LF/CRLF của Git trên
  Windows.

## Trạng thái và giới hạn

Boundary `documents` đã được khóa offline. Full suite và live model-service
smoke chưa chạy trong iteration này; production golden parity vẫn cần endpoint,
credential và catalog production nằm ngoài checkout hiện tại.
