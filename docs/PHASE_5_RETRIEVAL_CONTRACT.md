# Phase 5 — Contract retrieval và evidence

## Phạm vi lát cắt

Lát cắt này chuẩn hóa boundary retrieval theo Clean Code: application chỉ nhận
`ChunkHit` và `EvidenceBundle`, không biết object của Chroma hay SDK cụ thể.
`ChunkRetriever` là async port để các adapter dense, lexical hoặc hybrid có thể
thay thế nhau.

## Quy tắc đã thực thi

- Hit phải có source/chunk reference, rank dương và retrieval version.
- Các score nếu có phải là số hữu hạn.
- Metadata và source text được copy rồi khóa read-only để tránh mutation sau validate.
- Evidence rỗng bắt buộc có `insufficiency_reason` rõ ràng.
- Evidence có hit không được đồng thời gắn lý do thiếu bằng chứng.
- Chưa kết nối Chroma, legacy catalog hay FastAPI route trong lát cắt này.

## Bằng chứng kiểm thử

Lệnh và kết quả xác minh:

```text
`uv run pytest tests/test_phase_5_retrieval_contract.py` → **6 passed**.

`uv run pytest` → **95 passed, 2 skipped, 1 warning**. Hai test skip là do
Gradio và sample source không có trong checkout, không phải regression của lát cắt.

`uv run python -m compileall -q src tests` → **pass**.

`git diff --check` → **pass**.
```

Kết quả được ghi nhận trong handoff của iteration hiện tại; kiểm thử live
provider/model không thuộc phạm vi contract offline.
