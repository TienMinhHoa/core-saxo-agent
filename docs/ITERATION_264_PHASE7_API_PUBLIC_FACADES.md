# Iteration 264 - API dùng public facade của application

## Mục tiêu

Khóa nốt một điểm coupling trong Phase 7: inbound adapter `saxophone.interfaces.api`
không import trực tiếp models/ports/use case triển khai của chat, ingestion,
retrieval hoặc workflows.

## Thay đổi

- Thêm `ImageArtifactGate` vào public facade `saxophone.chat`.
- Chuyển API sang import từ các facade `saxophone.chat`, `saxophone.ingestion`,
  `saxophone.retrieval` và `saxophone.workflows`.
- Thêm AST contract test để phát hiện API quay lại import implementation module.

## Bằng chứng

- Trước thay đổi, test mới phát hiện **7 import vi phạm**.
- Sau thay đổi: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`
  đạt **27 passed**.
- Đã chạy thêm `uv run pytest`, `uv run python -m compileall -q src tests` và
  `git diff --check`; kết quả được ghi nhận trong handoff của iteration.

## Giới hạn xác minh

Đây là kiểm tra offline/static và không thay thế live model-service smoke hoặc
production parity. Hai kiểm tra đó vẫn bị chặn bởi endpoint, credential và
production catalog không có trong checkout hiện tại.
