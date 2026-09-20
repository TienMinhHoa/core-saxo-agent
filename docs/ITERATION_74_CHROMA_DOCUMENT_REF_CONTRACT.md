# Iteration 74 — contract `document_ref` trước khi reconcile Chroma

## Phạm vi

Lát cắt này tiếp tục siết fail-closed ở `ChromaVectorIndex`. Hàm
`list_chunk_ids()` dùng `document_ref` làm scope để đọc ID cũ trước khi
reconcile ingestion. Trước đây giá trị rỗng, chỉ chứa whitespace hoặc sai kiểu
vẫn được gửi xuống Chroma, làm boundary phụ thuộc vào lỗi của provider.

## Thay đổi

- Bổ sung `_validated_document_ref()` trong adapter ingestion.
- Từ chối `document_ref` không phải chuỗi hoặc chuỗi blank trước
  `collection.get()`; không có provider I/O khi input sai.
- Giữ nguyên giá trị chuỗi hợp lệ khi tạo filter `{"document_ref": ...}` để
  không thay đổi identity đã persist.
- Bổ sung 4 regression cases TDD cho `""`, whitespace, số và `None`.

## Bằng chứng

```text
uv run pytest tests/test_phase_4_ingestion_contract.py -k "list_chunk_ids" --basetemp=.pytest-tmp-74
7 passed, 32 deselected
```

Kết quả trên bao gồm test happy path và các test malformed provider IDs hiện có.
Full suite đạt **425 passed, 2 skipped**; `compileall` và `git diff --check`
đều thành công. Live model-service smoke và production golden parity vẫn chưa thể
chạy vì checkout chưa có endpoint, credential và catalog production thật.
