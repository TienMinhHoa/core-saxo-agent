# Iteration 106 — Khóa `document_ref` tại process-and-ingest

## Mục tiêu

Hoàn thiện cùng một policy path-safety cho toàn bộ API workflow tài liệu. Hai
route `process` và `source` đã chặn `document_ref` không an toàn; route kết hợp
`process-and-ingest` còn thiếu guard trước khi gọi workflow.

## Thay đổi

- Gọi `_require_safe_document_reference()` ngay sau khi normalize
  `document_ref` trong `POST /api/v1/documents/{document_ref}/process-and-ingest`.
- Thêm regression test với `..\\outside` (URL-encoded) để chứng minh request bị
  trả `422 unsafe document_ref`.
- Test cũng xác nhận extractor và vector index không bị gọi khi boundary reject
  input, tránh đọc artifact hoặc ghi dữ liệu trước khi kiểm tra path.

## Bằng chứng kiểm thử

- Red test trước khi sửa: request đi vào workflow và chỉ thất bại muộn do
  document reference trong extraction result không khớp request.
- Sau khi sửa: test mới và 28 test API route đều đạt.
- Full suite đạt **499 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` đều đạt.

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
