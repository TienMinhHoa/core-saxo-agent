# Phase 4 — Boundary trước embedding của `IndexDocument`

## Kết quả iteration 49

Đã chọn hướng Clean Code: `IndexDocument` nhận `IndexInputRecord`, một DTO chưa
có vector. Use case gọi `EmbeddingProvider`, kiểm tra `chunk_id`, source version
và model profile; chỉ sau đó mới tạo `ChunkIndexRecord` để gửi qua `VectorIndex`.

Điều này giữ đúng luồng một chiều `source -> embedding -> index` và loại bỏ
việc dùng `ChunkIndexRecord` có vector giả làm input cho application use case.

## Bằng chứng

- `tests/test_phase_4_index_document.py` đã được chuyển sang fixture
  `IndexInputRecord`; fake provider vẫn xác nhận input là `(chunk_id, text)`.
- `uv run pytest tests/test_phase_4_index_document.py -q`: **9 passed**.
- Chưa claim end-to-end: route API vẫn dựng `ChunkIndexRecord` trực tiếp và
  workflow đầy đủ `extract -> paragraph -> tag -> embed -> index` còn là lát
  cắt tiếp theo.
