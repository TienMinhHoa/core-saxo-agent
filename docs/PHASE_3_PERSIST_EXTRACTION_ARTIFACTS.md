# Phase 3 - Persist output artifacts của extraction

## Mục tiêu

Khép một phần khoảng trống sau `ProcessDocument`: khi hệ thống đã có
`PdfExtractionResult` và payload bytes tương ứng, application layer phải kiểm
tra đủ ba output (`markdown`, `layout`, `manifest`) trước khi giao từng artifact
cho `ArtifactRepository`.

## Thay đổi

- Thêm `PersistExtractionArtifacts` tại
  `saxophone.extraction.persistence`.
- Use case yêu cầu payload cho đủ ba tên output, kiểm tra kiểu `bytes`, kích
  thước và SHA-256 theo `ArtifactRef` trước lần ghi đầu tiên.
- Use case không biết filesystem, Chroma hay provider; storage vẫn thuộc port
  `ArtifactRepository`.
- Payload transfer từ remote service chưa được tự động nối vào workflow vì
  `PdfExtractionResult` hiện chỉ mang `ArtifactRef`, chưa mang bytes hoặc
  transfer handle. Slice này tạo boundary an toàn để nối adapter transfer ở
  bước sau.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_persist_extraction_artifacts.py
3 passed
```

Các contract đã kiểm tra: ghi đủ ba artifact, từ chối thiếu payload, và không
ghi gì khi payload sai integrity.

## Giới hạn còn lại

`ProcessDocument` chưa gọi use case này trong production flow vì remote model
adapter hiện chỉ trả metadata `ArtifactRef`. Cần bổ sung contract transfer
artifact (hoặc payload envelope) trước khi wiring end-to-end; không được giả
định bytes từ metadata.
