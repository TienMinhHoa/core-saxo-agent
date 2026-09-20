# Bằng chứng Iteration 150 — kiểm tra kiểu runtime của request extraction

## Phạm vi

`RemotePdfExtractor.extract()` là ranh giới nhận request từ application layer
trước khi tạo `ModelRequest` và gọi model service. Trước thay đổi, một object
sai kiểu có thể làm lộ `AttributeError` khi truy cập `document_ref`, thay vì
một lỗi contract rõ ràng.

## Thay đổi

- Thêm guard fail-closed yêu cầu request là `PdfExtractionRequest`.
- Request sai kiểu bị từ chối bằng `ValueError` trước mọi provider I/O.
- Thêm regression test chứng minh provider không bị gọi khi request không hợp lệ.

## Kiểm chứng

- Red test trước implementation: `10 passed, 1 failed`, thất bại đúng tại
  `AttributeError` của request sai kiểu.
- Targeted sau implementation: `11 passed` tại
  `tests/test_phase_3_remote_pdf_extractor.py`.
- Full suite, compileall và `git diff --check` được chạy sau khi hoàn thiện.

## Giới hạn kiểm chứng

Đây là kiểm chứng offline với fake model client. Live model-service smoke và
production golden parity vẫn chưa thực hiện vì checkout chưa có endpoint,
credential và catalog production được phê duyệt.
