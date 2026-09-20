# Iteration 60 — xác thực kết quả Chroma

## Phạm vi

Siết boundary của `ChromaSemanticRetriever` theo yêu cầu source/evidence-first
trong kế hoạch kiến trúc. Kết quả từ Chroma phải có đủ bốn field dạng một hàng
(`ids`, `documents`, `metadatas`, `distances`), có cùng chiều dài và khoảng cách
phải là số hữu hạn.

## Thay đổi

- Loại bỏ việc âm thầm biến response thiếu hoặc sai shape thành danh sách hit rỗng.
- Từ chối response thiếu field, sai nesting, lệch chiều dài hoặc distance là
  `NaN`/`inf` bằng `ValueError` có ngữ cảnh `Chroma result`.
- Giữ nguyên mapping hợp lệ sang `ChunkHit`, score semantic và bounded blocking I/O.
- Bổ sung test regression cho response thiếu field, sai shape và distance không hữu hạn.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_chroma_semantic_retriever.py -q`: **11 passed**.
- Chưa chạy full suite trong iteration này; cần chạy ở bước review/iteration kế tiếp.
- Chưa có live model-service smoke vì checkout vẫn thiếu endpoint và credential thật.

## Kết luận

Lát refactor này đạt mục tiêu nhỏ: malformed provider output không còn bị nuốt
thành kết quả rỗng, giúp workflow phát hiện lỗi contract sớm thay vì tạo evidence
không đáng tin cậy.
