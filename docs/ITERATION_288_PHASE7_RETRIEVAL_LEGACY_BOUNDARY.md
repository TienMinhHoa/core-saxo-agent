# Iteration 288 — cô lập compatibility boundary của retrieval legacy

## Phạm vi

Slice nhỏ này xử lý import trực tiếp `music_rag` còn sót trong
`src/saxophone/retrieval/adapters.py`. Retrieval application vẫn giữ nguyên
behavior legacy để phục vụ strangler migration, nhưng adapter chung không còn
biết trực tiếp module runtime legacy.

## Thay đổi

- Tạo `saxophone.retrieval.legacy` làm compatibility boundary duy nhất cho
  `CatalogStore` và `semantic_search` của `music_rag`.
- Cập nhật `LegacySemanticRetriever` dùng các symbol từ boundary này.
- Mở rộng AST enforcement: `retrieval/adapters.py` không được import
  `music_rag`, còn `retrieval/legacy.py` là file compatibility được phép duy
  trì trong giai đoạn migration.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py
  tests/test_hybrid_retrieval.py -q` → **47 passed**.
- Full suite: `uv run pytest -q` → **970 passed, 18 skipped, 1 warning**.
- Bytecode: `python -m compileall -q app.py src tests` → thành công.
- Hygiene: `git diff --check` → không có lỗi whitespace.

Các test skip là do Gradio, sample source hoặc quyền tạo symbolic link trên
môi trường Windows hiện tại; không liên quan slice này. Live model-service
smoke và production golden parity vẫn chưa xác minh vì checkout không có
endpoint, credential và catalog production thật.

## Kết luận

Slice này đạt mục tiêu Phase 7 về dependency enforcement cho retrieval: import
legacy đã được đặt sau một boundary có tên và có guard hồi quy. Chưa đánh dấu
hoàn tất toàn bộ kiến trúc vì live smoke/parity vẫn là blocker môi trường.
