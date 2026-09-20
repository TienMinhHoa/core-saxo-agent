# Iteration 132 — Contract `document_ref` tại extraction boundary

## Phạm vi

Đồng bộ `PdfExtractionRequest` và `PdfExtractionResult` với policy dùng chung
`is_safe_document_reference`. Đây là một bước hardening nhỏ trong Phase 3:
DTO extraction không được chấp nhận document identity có thể trở thành path
component không an toàn hoặc có biểu diễn Unicode không canonical.

## Thay đổi

- Hai DTO fail-closed khi `document_ref` chứa path traversal, dấu `/`, control
  character hoặc Unicode không ở dạng NFC.
- Giữ nguyên document reference NFC hợp lệ và các contract artifact/kind hiện có.
- Bổ sung test cho cả request và result; test chạy trước thay đổi implementation
  đã fail đúng 8 case, sau implementation pass đầy đủ.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_extraction_contract.py -q --basetemp=.pytest-tmp
14 passed
```

Đơn vị này chưa chứng minh live model-service smoke hay production golden
parity; checkout hiện chưa có endpoint, credential và catalog production cần
thiết để chạy hai kiểm tra đó.
