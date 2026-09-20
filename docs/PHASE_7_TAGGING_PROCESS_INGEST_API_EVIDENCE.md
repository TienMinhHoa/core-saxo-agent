# Phase 7 — Bằng chứng API process-and-ingest có tagging

Iteration 60 bổ sung acceptance test offline cho nhánh tagging của
`POST /api/v1/documents/{document_ref}/process-and-ingest`.

Test `test_process_and_ingest_route_preserves_tagging_before_indexing` dùng
fake artifact repository, extractor, tag/persist boundary, embedding provider
và vector index. Request truyền `tagging_profile=tags-v1`; kết quả chứng minh
tagging chạy trước embedding/indexing và tag `music` được giữ trong metadata
vector.

Đây là bằng chứng wiring và provenance trong app. Test không gọi model service
thật, nên chưa phải live model smoke hoặc production Chroma verification.
