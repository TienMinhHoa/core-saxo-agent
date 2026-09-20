# Iteration 91 — Hợp đồng vector truy vấn Chroma Semantic Retriever

## Mục tiêu

Khóa biên an toàn giữa embedding provider và Chroma semantic retriever. Provider
phải trả đúng một vector không rỗng, gồm các số hữu hạn; dữ liệu sai không được
đi tiếp tới Chroma.

## Thay đổi

- Thêm `_validated_embedding_output` tại `ChromaSemanticRetriever`.
- Từ chối kết quả rỗng, nhiều vector, vector rỗng, `bool`, `NaN`, `inf` hoặc
  kiểu phần tử không phải số.
- Chuẩn hóa số hợp lệ thành `list[float]` trước khi gửi `query_embeddings`.
- Bổ sung 5 regression cases, đồng thời xác nhận collection không bị gọi khi
  output embedding sai.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_chroma_semantic_retriever.py -q`
- Kết quả: **33 passed**.

## Trạng thái và giới hạn

Contract offline đã được khóa ở adapter. Chưa chạy live model-service hoặc
production parity vì checkout hiện không có endpoint, credential và catalog
production được cung cấp.
