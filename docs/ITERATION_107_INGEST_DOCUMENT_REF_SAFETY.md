# Iteration 107 — Khóa `document_ref` tại route ingest

## Mục tiêu

Đồng nhất policy path-safety cho route `POST /api/v1/documents/{document_ref}/ingest`.
Route này trước đó chỉ normalize giá trị rồi dựng command/index records, nên một
reference chứa path traversal vẫn có thể đi vào ingestion boundary.

## Thay đổi

- Gọi `_require_safe_document_reference()` ngay sau bước normalize trong route
  ingest, trước khi tạo command hoặc record và trước khi gọi `IndexDocument`.
- Thêm regression test với `..\outside` được URL-encode, xác minh trả `422` và
  không gọi embedding provider hoặc vector index.

## Bằng chứng kiểm thử

- Red test trước khi sửa: request traversal trả `200`, chứng minh gap tồn tại.
- Sau khi sửa: targeted API test pass.
- Full pytest, compileall và `git diff --check` được chạy sau thay đổi.

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh vì checkout
chưa có endpoint, credential và catalog production thật.
