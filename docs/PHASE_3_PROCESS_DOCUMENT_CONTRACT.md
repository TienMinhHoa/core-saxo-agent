# Phase 3 — ProcessDocument và cổng kiểm tra source artifact

## Mục tiêu

Iteration này chọn một lát cắt nhỏ của document workflow: trước khi gọi
`PdfExtractor`, application phải chứng minh source PDF tồn tại trong
`ArtifactRepository` và payload có đúng kích thước đã khai báo trong
`ArtifactRef`.

Use case mới là `saxophone.workflows.process_document.ProcessDocument`. Nó
nhận `PdfExtractionRequest`, đọc artifact qua port bất đồng bộ, rồi mới ủy
quyền cho `PdfExtractor`. Use case không biết FastAPI, Chroma, filesystem hay
SDK model.

## Luồng và quy tắc

```text
PdfExtractionRequest
        |
        v
ArtifactRepository.get(source)
        |
        +-- thiếu artifact -> FileNotFoundError, không gọi extractor
        +-- sai size       -> ValueError, không gọi extractor
        `-- hợp lệ         -> PdfExtractor.extract(request)
```

Checksum vẫn thuộc trách nhiệm adapter `ArtifactRepository` (ví dụ
`LocalArtifactRepository` đã kiểm tra SHA-256 khi ghi). Use case giữ thêm
kiểm tra kích thước ở boundary để không gửi payload rõ ràng sai metadata sang
remote extraction service.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_3_process_document.py -q`: **2 passed**.
- `uv run pytest -q`: **143 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src`: đạt.
- `git diff --check`: đạt.

Hai test mới chứng minh source hợp lệ được chuyển tiếp đúng request và source
không tồn tại bị chặn trước khi extractor được gọi. Route FastAPI chưa được
wiring sang use case này trong lát cắt hiện tại; bước kế tiếp là đưa
`ArtifactRepository` và `ProcessDocument` vào `AppContainer`, sau đó đổi route
process sang gọi application workflow.
