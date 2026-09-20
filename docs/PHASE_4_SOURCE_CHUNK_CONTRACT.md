# Hợp đồng chunk nguồn trước embedding — Phase 4

## Phạm vi iteration 38

Iteration này chọn lát nhỏ theo hướng Clean Code: chuẩn hóa một chunk nguồn
trước khi tagging, gọi embedding và ghi vector index. Đây là bước đầu của
pipeline trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:

```text
load manifest -> normalize source blocks -> chunk -> tagging -> embedding -> index
```

## Thay đổi

`IngestionSourceChunk` trong `src/saxophone/ingestion/models.py` là DTO bất
biến cho dữ liệu đã normalize nhưng chưa có vector. DTO giữ:

- `chunk_id`, `document_ref`, `source_version` và `access_scope`;
- `search_text` không rỗng;
- `metadata` dạng mapping và được copy thành mapping chỉ đọc.

`ChunkIndexRecord` vẫn đại diện cho projection đã sẵn sàng ghi index. Vì vậy
API không cần tạo embedding giả chỉ để biểu diễn source chunk ở bước trước
embedding.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_ingestion_contract.py -q`: **16 passed**.
- Test bao phủ DTO hợp lệ, metadata bất biến, trường định danh rỗng và
  metadata sai kiểu.

## Giới hạn còn lại

DTO mới chưa được nối vào route ingest hoặc workflow đọc extraction manifest.
Lát tiếp theo cần tạo parser deterministic từ manifest sang
`IngestionSourceChunk`, rồi mới nối use case embedding/index; không được đánh
đồng ingestion hoàn chỉnh chỉ vì contract này đã tồn tại.
