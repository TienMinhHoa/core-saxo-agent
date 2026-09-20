# Iteration 61 — Fail-closed validation cho Chroma `chunk_id`

## Phạm vi

Lát refactor này siết một lỗi nhỏ tại ranh giới `ChromaSemanticRetriever`: provider
không được trả về `chunk_id` rỗng, chỉ chứa whitespace, hoặc khác kiểu chuỗi. Trước
đây mapper âm thầm bỏ qua các phần tử đó, khiến kết quả trả về ít hơn dữ liệu provider
mà không có lỗi rõ ràng.

## Thay đổi

- `ChromaSemanticRetriever._map_hits` nay ném `ValueError` nếu `chunk_id` không phải
  chuỗi non-blank.
- Bổ sung test cho `""`, chuỗi whitespace, số nguyên và boolean.
- Giữ nguyên mapping hợp lệ và contract `ChunkHit` provider-independent.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_chroma_semantic_retriever.py -q`: **15 passed**.
- `git diff --check`: đạt; chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên Windows.

## Ý nghĩa với kiến trúc mục tiêu

Result từ adapter phải được validate trước khi đi vào retrieval application và evidence
bundle. Fail-closed tại đây tránh việc dữ liệu malformed bị biến thành evidence thiếu
một cách im lặng, phù hợp yêu cầu result validation trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.

## Còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì checkout
chưa có endpoint, credential và catalog production thật.
