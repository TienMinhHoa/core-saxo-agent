# Phase 4 — workflow ingest output extraction

## Mục tiêu

Iteration 55 chọn hướng Clean Code: tạo một workflow nhỏ nối output Markdown đã
được lưu bởi extraction với cổng ingestion/indexing. Caller không còn phải tự
đọc file hay tự dựng `IndexInputRecord` từ Markdown.

## Thay đổi

- Thêm `IngestExtractedDocument` tại
  `src/saxophone/workflows/ingest_extracted_document.py`.
- Workflow đọc Markdown qua `ArtifactRepository`, giải mã UTF-8, dùng
  `build_source_chunks` để giữ heading/page metadata và tạo record trước
  embedding.
- Workflow chuyển tiếp sang `IndexDocument`, nên embedding và vector index vẫn
  nằm sau port, không kéo SDK provider vào workflow.
- Chỉ chấp nhận profile chunking đã có implementation (`header-v1`); profile
  lạ bị từ chối rõ ràng, không fallback im lặng.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_ingest_extracted_document.py -q`: **2 passed**.
- Test happy path chứng minh Markdown persisted trở thành một index record,
  giữ nguyên source text và không tạo vector giả.
- Test lỗi chứng minh chunking profile không hỗ trợ bị từ chối trước khi index.

## Phạm vi còn lại

Workflow này mới hoàn tất projection Markdown → index input. Paragraph tagging
LLM và route API để gọi workflow liên tục sau extraction vẫn là bước kế tiếp;
iteration này không claim ingestion end-to-end hay live model-service.
