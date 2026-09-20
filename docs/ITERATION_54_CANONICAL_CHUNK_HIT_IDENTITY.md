# Iteration 54 — Canonical identity của `ChunkHit`

## Phạm vi

Siết contract retrieval ở DTO `ChunkHit`. Ba định danh `source_ref`, `chunk_ref`
và `retrieval_version` là dữ liệu provenance đi qua nhiều boundary, vì vậy phải
ở dạng chuỗi non-blank, không có khoảng trắng đầu/cuối và đã Unicode NFC
canonical trước khi `EvidenceBundle` sử dụng chúng.

## Thay đổi

- Bổ sung validation canonical cho cả ba identity field trong
  `src/saxophone/retrieval/models.py`.
- Bổ sung 9 regression cases theo TDD trong
  `tests/test_phase_5_retrieval_contract.py`: khoảng trắng đầu/cuối và Unicode
  decomposed đều bị từ chối.

## Bằng chứng

- Test targeted: `uv run pytest tests/test_phase_5_retrieval_contract.py -q` →
  **18 passed**.
- Trước implementation, 9 test mới fail đúng vì `ChunkHit` chưa có canonical
  guard; sau implementation toàn bộ test pass.
- Full suite, compileall và `git diff --check` được chạy sau khi hoàn tất slice.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout chưa có endpoint, credential và catalog production thật.
