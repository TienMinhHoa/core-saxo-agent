# Phase 3 — Adapter payload extraction qua repository

## Phạm vi iteration 54

Iteration này chọn hướng Clean Code: triển khai adapter nhỏ nhất để workflow
`ProcessAndPersistDocument` lấy payload `markdown`, `layout`, `manifest` qua
`ArtifactRepository`, thay vì biết filesystem hoặc SDK của model service.

## Thay đổi

- Thêm `RepositoryExtractionArtifactPayloadProvider` trong
  `saxophone.extraction.persistence`.
- Adapter đọc đúng ba `ArtifactRef` đã được `PdfExtractionResult` xác thực và
  trả về mapping tên → `bytes`; lỗi thiếu artifact được truyền lên để workflow
  không ghi dữ liệu giả.
- Composition root tự compose `ProcessAndPersistDocument` với adapter này khi
  chạy production mặc định.
- Nếu test/integration truyền tường minh `process_document`, compatibility path
  cũ vẫn được giữ; không đổi hành vi ngoài scope.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_repository_payload_provider.py tests/test_phase_1_composition_root.py tests/test_phase_3_process_and_persist_document.py tests/test_phase_7_api_routes.py -q
28 passed, 1 warning

uv run pytest -q
221 passed, 2 skipped, 1 warning

python -m compileall -q src
git diff --check
```

Hai test skip là do Gradio và sample source không có trong checkout hiện tại;
không phải regression của iteration này.

## Ranh giới còn lại

Adapter này chỉ hoàn thiện đường đọc payload từ kho artifact backend-owned.
Contract hiện tại chưa mô tả endpoint/URI download từ remote model service, nên
chưa claim live upload → extraction → persist → ingest → indexed end-to-end.
Lát cắt tiếp theo cần bổ sung remote artifact transfer contract/adapter trước
khi có thể kiểm chứng live flow.
