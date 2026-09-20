# Phase 3 - Workflow extraction và persist artifact

## Mục tiêu

Nối hai boundary đã có thành một coordinator có thể kiểm thử: xác minh source PDF,
gọi extractor, lấy payload qua một port transfer có kiểm soát, rồi persist đủ ba
artifact `markdown`, `layout`, `manifest`.

## Thay đổi

- Thêm `ExtractionArtifactPayloadProvider` để workflow không biết filesystem dùng
  chung hoặc SDK của model service.
- Thêm `ProcessAndPersistDocument`; coordinator chỉ ghép
  `ProcessDocument` và `PersistExtractionArtifacts`.
- Payload vẫn bị kiểm tra kiểu `bytes`, kích thước và SHA-256 trước khi ghi; thiếu
  payload không tạo ra partial write.
- Không thêm job lifecycle, background worker hoặc GPU runtime vào backend.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_process_and_persist_document.py tests/test_phase_3_process_document.py
9 passed
```

Test chứng minh transfer đủ ba output và reject payload thiếu trước khi ghi output.

## Giới hạn còn lại

`RemotePdfExtractor` hiện vẫn trả metadata `ArtifactRef`; adapter transfer thật và
wiring coordinator vào route production sẽ là lát tiếp theo. Không coi artifact
metadata là payload bytes và chưa tuyên bố upload → indexed end-to-end hoàn tất.
