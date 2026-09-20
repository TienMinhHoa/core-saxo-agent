# Phase 7 — Kiểm tra chữ ký PDF trước khi ghi artifact

## Phạm vi

Route `POST /api/v1/documents/{document_ref}/source` trước đây chỉ tin vào
`Content-Type: application/pdf`. Lát cắt này bổ sung kiểm tra chữ ký `%PDF-`
trong 1024 byte đầu của payload, sau khi đã áp dụng giới hạn kích thước.

Nếu chữ ký không hợp lệ, API trả `422` và không gọi
`ArtifactRepository.put`. Tên file từ client vẫn không được dùng để tạo path.

## Bằng chứng

- Test hồi quy `test_source_upload_rejects_pdf_mime_spoof_without_persisting`:
  MIME là PDF nhưng payload giả bị từ chối và repository không nhận ghi.
- Test upload PDF hiện có tiếp tục xác nhận payload có header `%PDF-` được lưu
  thành `ArtifactRef` với checksum và kích thước đúng.

## Giới hạn xác minh

Đây là kiểm tra offline ở API boundary; chưa thay thế parser PDF đầy đủ hoặc
live smoke với model service.
