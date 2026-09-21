# Iteration 262 — Public facade cho tagging

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: module `tagging`
cần có một application facade ổn định để consumer không phụ thuộc trực tiếp vào
`models`, `ports`, `parser` hoặc `use_cases` nội bộ. Composition root vẫn được
phép nối các adapter cụ thể.

## Thay đổi

- Mở rộng `saxophone.tagging` thành facade công khai cho DTO, ports, tagging
  use cases, parser, remote adapters và JSON repositories.
- Chuyển `ingestion.use_cases` sang lấy `ParagraphBlock`, `TaggedParagraph` và
  `TagAndPersistParagraph` từ facade.
- Chuyển `workflows.ingest_extracted_document` sang lấy
  `parse_chunk_paragraphs` từ facade.
- Dùng lazy export cho use case/parser để tránh vòng import giữa `tagging` và
  `ingestion`.
- Thêm AST/public-export contract tests để ngăn consumer quay lại import module
  implementation.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **24 passed**.
- `uv run pytest -q`: **945 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

Các test skip vẫn là các điều kiện môi trường đã biết (Gradio/fixture thiếu và
Windows không có quyền tạo symbolic link), không phải lỗi của facade.

## Trạng thái và giới hạn

Đã khóa boundary tagging offline. Stop condition toàn repository chưa đạt vì
live model-service smoke và production golden parity vẫn cần endpoint,
credential và catalog production thật ngoài checkout hiện tại.
