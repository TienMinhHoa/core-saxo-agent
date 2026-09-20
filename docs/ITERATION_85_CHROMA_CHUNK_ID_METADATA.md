# Iteration 85 — metadata Chroma giữ canonical `chunk_id`

## Phạm vi

Đối chiếu mục 11.2 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: logical
Chroma record phải có `chunk_id` trong metadata projection, bên cạnh `id` của
record. Iteration này chỉ xử lý contract nhỏ đó, không thay đổi backend lưu trữ.

## Thay đổi

- `ChromaVectorIndex._metadata()` luôn ghi `chunk_id` lấy từ
  `ChunkIndexRecord` vào metadata gửi cho Chroma.
- `chunk_id` được coi là reserved metadata key; metadata do caller cung cấp
  không được phép ghi đè canonical identity.
- Bổ sung contract test cho metadata projection và test fail-closed khi caller
  gửi `chunk_id` trong metadata riêng.

## Bằng chứng kiểm chứng

```text
uv run pytest tests/test_phase_4_ingestion_contract.py -q
71 passed
```

Test chứng minh provider nhận `metadatas[0]["chunk_id"]` đúng với record ID và
không bị gọi khi metadata chứa reserved `chunk_id`.

Live Chroma/model-service smoke và production parity chưa được chạy trong
checkout này vì vẫn thiếu endpoint, credential và catalog production thật.
