# Iteration 59 — hợp đồng retrieval version của Chroma adapter

## Phạm vi

Siết một ranh giới nhỏ trong `ChromaSemanticRetriever`: `retrieval_version`
phải là chuỗi không rỗng và canonical (không có whitespace thừa, Unicode ở
dạng NFC). Điều này giữ nhất quán với `ChunkHit` và `EvidenceBundle`, tránh
đưa version không ổn định vào provenance của evidence.

## Thay đổi

- Adapter từ chối giá trị không phải chuỗi, rỗng, có whitespace đầu/cuối hoặc
  Unicode chưa chuẩn hóa.
- Bổ sung regression tests cho cả lỗi kiểu dữ liệu và ba dạng version không
  canonical.
- Không thay đổi đường đi search thành công hoặc mapping kết quả Chroma.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_chroma_semantic_retriever.py` — 8 passed.
- Full suite: `uv run pytest -q` — 383 passed, 2 skipped, 1 warning.
- Live Chroma/model-service smoke: chưa chạy trong checkout này; không có
  endpoint/credential production được cung cấp.
