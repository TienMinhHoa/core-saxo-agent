# Trạng thái nghiệm thu refactor kiến trúc

Tài liệu này là bảng đối chiếu giữa `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` và
checkout hiện tại. Lựa chọn triển khai là **Clean Code modular monolith** với
strangler migration: giữ các module legacy làm compatibility/reference cho đến
khi có feature parity và quyết định migration riêng.

## Kết luận ngắn

- Các capability đích đã có trong package `src/saxophone`: composition root,
  extraction, ingestion, retrieval, chat, tagging, workflow và API adapters.
- Bằng chứng offline hiện tại: `uv run pytest` đạt **285 passed, 2 skipped**;
  `compileall` và `git diff --check` đã được chạy ở lát cắt gần nhất.
- Chưa được phép kết luận production-ready: checkout không có remote
  model-service endpoint/credential để chạy live smoke thật. Trạng thái này
  được tách riêng tại `LIVE_MODEL_SERVICE_SMOKE_STATUS.md`.

## Đối chiếu tiêu chí bắt buộc

| # | Tiêu chí | Trạng thái | Bằng chứng chính |
|---:|---|---|---|
| 1 | Một ASGI entrypoint và composition root | Đạt offline | `src/saxophone/main.py`, `app/factory.py`; `test_phase_7_backend_entrypoint.py` |
| 2 | Public API rõ cho extraction/ingestion/retrieval/chat | Đạt offline | `src/saxophone/*`; nhóm test Phase 3–6 |
| 3 | Route không import SDK provider/database/GPU | Đạt offline | `test_phase_7_dependency_enforcement.py` |
| 4 | Use case chạy qua fake ports | Đạt offline | `test_phase_2_*`, `test_phase_4_*`, `test_retrieve_evidence.py`, `test_chat_answer_question.py` |
| 5 | Chroma chỉ là search-index adapter | Đạt offline | `platform/chroma.py`, `test_chroma_sidecar_contract.py`, `test_phase_1_chroma_live_contract.py` |
| 6 | Upload có workflow đến trạng thái indexed | Đạt offline | `/documents/{document_ref}/process-and-ingest`, `test_phase_3_process_and_persist_document.py`, `test_phase_4_ingest_extracted_document.py` |
| 7 | Process/ingest trả typed result/error, không job lifecycle | Đạt offline | `test_phase_3_process_document.py`, `test_phase_7_process_and_ingest_route.py` |
| 8 | Retrieval tạo và validate `EvidenceBundle` | Đạt offline | `retrieval/use_cases.py`, `test_retrieve_evidence.py` |
| 9 | Tagging nằm trong ingestion và dùng `ChunkRetriever` boundary | Đạt offline | `tagging/*`, `test_phase_8_*`, `test_phase_4_ingest_extracted_document.py` |
| 10 | Hybrid-ready retrieval | Đạt offline | `retrieval/adapters.py` có `InMemoryLexicalRetriever` và `HybridRetriever` (RRF); `tests/test_hybrid_retrieval.py` |
| 11 | Giữ provenance/page/layout/image refs | Đạt offline | extraction models, Chroma sidecar contract và Phase 3/4 tests |
| 12 | Output model không hợp lệ không fallback im lặng | Đạt offline | `test_phase_1_model_response_json_validation.py` và remote adapter tests |
| 13 | Unit/contract/integration/API/golden offline | Đạt offline | `uv run pytest`: 285 passed, 2 skipped |
| 14 | Live model-service smoke được báo riêng | Đạt về tài liệu; chưa chạy live | `LIVE_MODEL_SERVICE_SMOKE_STATUS.md` |
| 15 | Legacy chỉ xóa sau parity và quyết định migration | Có compatibility adapter; đã có golden parity offline tối thiểu, chưa có parity production | `retrieval/adapters.py`, `tests/test_hybrid_retrieval.py`, `tests/fixtures/golden/legacy_retrieval/catalog.json`, `docs/LEGACY_RETRIEVAL_PARITY.md`; chưa retire legacy |
| 16 | Runtime đích không phụ thuộc frontend/UI | Đạt offline | `saxophone-api`, `test_phase_7_backend_entrypoint.py` |
| 17 | Health/event loop không bị chặn bởi blocking adapter | Đạt offline | `test_phase_7_bounded_blocking_io.py`, `test_phase_7_event_loop_responsiveness.py` |
| 18 | Chroma record giữ embedding, source document và metadata đã validate | Đạt offline | `test_chroma_sidecar_contract.py`, `test_phase_4_index_input_projection.py` |
| 19 | Backend chạy không GPU/CUDA/Paddle runtime | Đạt offline cho package đích | `test_phase_7_dependency_enforcement.py`; legacy extraction vẫn tách riêng |
| 20 | OCR/VLM/embedding/LLM qua `LiteLLMModelClient`, có retry/validation | Đạt offline cho adapter đích | `platform/model_client.py`, remote adapter tests; live provider chưa xác minh |
| 21 | Artifact URI/upload, size và checksum có kiểm soát | Đạt offline | `documents/models.py`, `platform/artifacts.py`, upload size/signature tests |

## Lệnh kiểm chứng

```text
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

Các lệnh trên chỉ chứng minh behavior offline và chất lượng checkout. Chúng
không chứng minh remote model-service thật, credential, TLS/network policy hay
deployment production.

## Ghi nhận iteration 2

- Đã bổ sung lexical retrieval adapter in-memory, đọc header/content/tags từ metadata và trả về `ChunkHit` provider-independent.
- Đã bổ sung `HybridRetriever` dùng Reciprocal Rank Fusion; kết quả giữ semantic score, keyword score, fused score và rank mới.
- Đã thêm unit tests cho lexical matching, RRF merge, filter forwarding và validation `rrf_k`.
- Xác minh: targeted retrieval tests **9 passed**; toàn bộ suite **287 passed, 2 skipped**. Live model-service smoke vẫn chưa thể chạy vì checkout chưa có endpoint/credential thật.

## Việc còn lại trước khi đóng refactor

### Iteration 8 — loại bỏ workflow job lifecycle lỗi thời

- Đã loại bỏ `WorkflowJob`, `JobStatus`, `remote_job_id` và export tương ứng khỏi
  package workflow; target chỉ còn direct request/response qua LiteLLM client.
- Bằng chứng tĩnh: không còn module hoặc contract test job lifecycle trong
  package `saxophone`; các use case workflow hiện hành không tham chiếu job state.
- Iteration 10 bổ sung source-only guard tại `test_phase_7_dependency_enforcement.py`;
  guard này bỏ qua `__pycache__` để không nhầm bytecode cũ là source hiện hành.
- Cần chạy lại full suite để xác nhận không có import ẩn; live smoke vẫn bị chặn
  bởi thiếu endpoint/credential thật.

1. Cung cấp endpoint và credential của model-service để chạy live smoke theo
   tài liệu riêng; cập nhật bằng chứng, không dùng fake HTTP để thay thế.
2. Quyết định có triển khai hybrid fusion và lập golden parity report trước khi
   deprecate legacy catalog/UI.
3. Khi hai điều trên đã có bằng chứng, cập nhật lại bảng này rồi mới đánh dấu
   stop condition là hoàn tất.
