# Phase 3 — Khóa loại và media type của source PDF

## Mục tiêu

Bảo đảm workflow extraction chỉ đọc và chuyển tiếp artifact có `kind=source_pdf`
và `media_type=application/pdf`. Artifact Markdown, layout hoặc media type khác
không được đi tới extractor.

## Thay đổi

- `ProcessDocument.execute` kiểm tra loại artifact và media type trước khi gọi
  repository hoặc `PdfExtractor`.
- Bổ sung test TDD chứng minh source không phải PDF bị từ chối trước khi extractor
  được gọi.
- Giữ validation `PdfExtractionRequest` cho `kind`; workflow tiếp tục bảo vệ
  boundary media type ở lớp orchestration.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_3_process_document.py -q`: **8 passed**.
- `uv run pytest -q`: **248 passed, 2 skipped**; 2 skip là fixture Gradio/sample
  source thiếu sẵn trong checkout, không phải regression.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển đổi newline CRLF của Git trên
  Windows.

## Giới hạn

Lát cắt này chưa xác minh live model service hoặc upload PDF qua browser; nó chỉ
khóa contract offline tại application workflow boundary.
