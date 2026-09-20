# Trạng thái nghiệm thu refactor kiến trúc

Tài liệu này là bảng đối chiếu giữa `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` và
checkout hiện tại. Lựa chọn triển khai là **Clean Code modular monolith** với
strangler migration: giữ các module legacy làm compatibility/reference cho đến
khi có feature parity và quyết định migration riêng.

## Kết luận ngắn

- Các capability đích đã có trong package `src/saxophone`: composition root,
  extraction, ingestion, retrieval, chat, tagging, workflow và API adapters.
- Bằng chứng offline hiện tại: `uv run pytest` đạt **425 passed, 2 skipped**;
  `compileall` và `git diff --check` đã được chạy ở lát cắt gần nhất.
- Chưa được phép kết luận production-ready: checkout không có remote
  model-service endpoint/credential để chạy live smoke thật. Trạng thái này
  được tách riêng tại `LIVE_MODEL_SERVICE_SMOKE_STATUS.md`.

### Iteration 156 — canonical contract của `ModelResponse`

- Siết `ModelResponse` để từ chối `model`, `response_schema` và
  `source_version` có whitespace đầu/cuối, control character/DEL hoặc Unicode
  chưa NFC; không còn `.strip()` âm thầm che khuất response drift.
- Regression tests cho 9 trường hợp không canonical; targeted adapter suite đạt
  **47 passed**. Chi tiết tại
  `docs/ITERATION_156_MODEL_RESPONSE_CANONICAL_CONTRACT.md`.

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
| 13 | Unit/contract/integration/API/golden offline | Đạt offline | `uv run pytest`: 425 passed, 2 skipped |
| 14 | Live model-service smoke được báo riêng | Đạt về tài liệu; chưa chạy live | `LIVE_MODEL_SERVICE_SMOKE_STATUS.md` |
| 15 | Legacy chỉ xóa sau parity và quyết định migration | Có compatibility adapter; đã có golden parity offline tối thiểu, chưa có parity production | `retrieval/adapters.py`, `tests/test_hybrid_retrieval.py`, `tests/fixtures/golden/legacy_retrieval/catalog.json`, `docs/LEGACY_RETRIEVAL_PARITY.md`; chưa retire legacy |
| 16 | Runtime đích không phụ thuộc frontend/UI | Đạt offline | `saxophone-api`, `test_phase_7_backend_entrypoint.py` |
| 17 | Health/event loop không bị chặn bởi blocking adapter | Đạt offline | `test_phase_7_bounded_blocking_io.py`, `test_phase_7_event_loop_responsiveness.py` |
| 18 | Chroma record giữ embedding, source document và metadata đã validate | Đạt offline | `test_chroma_sidecar_contract.py`, `test_phase_4_index_input_projection.py` |
| 19 | Backend chạy không GPU/CUDA/Paddle runtime | Đạt offline cho package đích | `test_phase_7_dependency_enforcement.py`; legacy extraction vẫn tách riêng |
| 20 | OCR/VLM/embedding/LLM qua `LiteLLMModelClient`, có retry/validation | Đạt offline cho adapter đích | `platform/model_client.py`, remote adapter tests; live provider chưa xác minh |
| 21 | Artifact URI/upload, size và checksum có kiểm soát | Đạt offline | `documents/models.py`, `platform/artifacts.py`, upload size/signature tests |

### Iteration 74 — validate `document_ref` trước Chroma reconcile

- `ChromaVectorIndex.list_chunk_ids()` hiện fail-closed với `document_ref` sai
  kiểu hoặc blank trước khi gọi `collection.get()`.
- Bổ sung 4 regression cases; targeted contract đạt **7 passed, 32 deselected**.
- Chi tiết: `docs/ITERATION_74_CHROMA_DOCUMENT_REF_CONTRACT.md`.
- Live model-service smoke và production golden parity vẫn bị chặn bởi thiếu
  endpoint, credential và catalog production thật.

## Lệnh kiểm chứng

```text
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

Các lệnh trên chỉ chứng minh behavior offline và chất lượng checkout. Chúng
không chứng minh remote model-service thật, credential, TLS/network policy hay
deployment production.

### Iteration 45 - chặn citations khi thiếu bằng chứng

- Siết `ChatResult`: trạng thái `INSUFFICIENT_EVIDENCE` phải có citations rỗng,
  tránh phát ra source refs khi không có evidence được grounding.
- Bổ sung regression test tại `tests/test_chat_answer_question.py`; happy path
  `ANSWERED` và nhánh không có hit vẫn giữ nguyên hành vi.
- Xác minh: targeted **9 passed**; full suite **341 passed, 2 skipped, 1
  warning**; `compileall` và `git diff --check` thành công.
- Chi tiết: `docs/ITERATION_45_CHAT_INSUFFICIENT_CITATIONS.md`.
- Live model-service smoke và production golden parity vẫn bị chặn bởi thiếu
  endpoint, credential và catalog production thật.

## Ghi nhận iteration 2

- Đã bổ sung lexical retrieval adapter in-memory, đọc header/content/tags từ metadata và trả về `ChunkHit` provider-independent.
- Đã bổ sung `HybridRetriever` dùng Reciprocal Rank Fusion; kết quả giữ semantic score, keyword score, fused score và rank mới.
- Đã thêm unit tests cho lexical matching, RRF merge, filter forwarding và validation `rrf_k`.
- Xác minh: targeted retrieval tests **9 passed**; toàn bộ suite **287 passed, 2 skipped**. Live model-service smoke vẫn chưa thể chạy vì checkout chưa có endpoint/credential thật.

### Iteration 52 - khóa kiểu refs tại EvidenceBundle

- `EvidenceBundle` từ chối `selected_refs` và `image_refs` không phải tuple,
  tránh chuỗi bị duyệt như danh sách ký tự tại retrieval → chat boundary.
- Test contract được viết trước implementation; targeted **9 passed**.
- Full suite hiện tại **347 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` đạt. Chi tiết: `docs/ITERATION_52_EVIDENCE_REF_TUPLE_CONTRACT.md`.

## Việc còn lại trước khi đóng refactor

### Iteration 23 - metrics tối thiểu cho structured events

- Đã thêm `EventMetrics` đếm request theo event/task/result và lưu duration theo
  task; `LoggingEventSink` cập nhật metrics trước khi ghi log.
- Composition root mặc định tạo và expose metrics qua `AppContainer.metrics`;
  không thay đổi đường override sink dành cho test.
- Xác minh iteration 23: targeted **29 passed**; full suite **314 passed, 2
  skipped, 1 warning**; `compileall` và `git diff --check` thành công.
- Chi tiết: `docs/ITERATION_23_EVENT_METRICS.md`.

### Iteration 25 — snapshot metrics nhất quán

- Bổ sung `MetricsSnapshot` bất biến và `EventMetrics.snapshot()` để đọc counts,
  duration, in-flight và peak concurrency dưới cùng một lock.
- Xác minh: targeted **9 passed**; full suite **316 passed, 2 skipped, 1
  warning**; `compileall` và `git diff --check` thành công.
- Chi tiết: `docs/ITERATION_25_METRICS_SNAPSHOT.md`.

### Iteration 26 — token usage và cost tùy chọn

- Mở rộng `StructuredEvent` với `input_tokens`, `output_tokens` và `cost_usd`
  tùy chọn; validate không âm và không làm lộ payload/secret.
- `EventMetrics` cộng dồn usage theo task và `MetricsSnapshot` giữ snapshot
  bất biến của token/cost cùng các metric hiện có.
- Contract test targeted: **14 passed**. Full suite, `compileall` và
  `git diff --check` được chạy ở bước xác minh cuối iteration.
- Chi tiết: `docs/ITERATION_26_USAGE_COST_METRICS.md`.

### Iteration 27 — enforcement ranh giới dependency

- Bổ sung AST source guard để chặn import ngược giữa các lớp business,
  application, interfaces và composition root; đồng thời giữ ranh giới riêng
  cho retrieval, chat và ingestion theo kiến trúc trong kế hoạch.
- Guard chỉ quét source hiện hành, bỏ qua `__pycache__`, nên không bị bytecode
  cũ làm nhiễu kết quả kiểm tra.
- Xác minh iteration 27: **323 passed, 2 skipped**; `compileall` và
  `git diff --check` thành công.
- Chi tiết: `docs/ITERATION_27_DEPENDENCY_LAYER_GUARD.md`.

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

### Iteration 76 — Chroma upsert khong chap nhan ID trung

- Siết `ChromaVectorIndex.upsert_chunks()` fail-closed khi cùng một
  `chunk_id` xuất hiện nhiều lần trong một batch, trước khi gọi provider.
- Bổ sung regression test chứng minh batch trùng ID không tạo provider I/O;
  chi tiết tại `docs/ITERATION_76_CHROMA_UPSERT_UNIQUE_IDS.md`.
- Xác minh offline: targeted **41 passed**; full suite **427 passed, 2
  skipped, 1 warning**; `compileall` và `git diff --check` thành công.
- Live model-service smoke và production golden parity vẫn bị chặn bởi thiếu
  endpoint, credential và catalog production thật.

### Iteration 11 — tôn trọng Retry-After của model-service

- `LiteLLMModelClient` đọc header `Retry-After` dạng số giây cho response
  transient; delay hiệu dụng là `max` giữa server delay và local backoff.
- Regression test được bổ sung trong `test_phase_1_litellm_client.py`; retry
  vẫn bị giới hạn bởi `max_attempts` và không áp dụng cho lỗi contract/auth.
- Xác minh offline: **286 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` đều thành công.
- Live model-service smoke vẫn chưa chạy vì checkout chưa có endpoint/credential
  thật; chi tiết lát thay đổi ở `ITERATION_11_RETRY_AFTER_CONTRACT.md`.

### Iteration 12 — chỉ nhận Retry-After hữu hạn

- `LiteLLMModelClient` hiện loại bỏ các giá trị `Retry-After` không hữu hạn
  (`nan`, `inf`) bên cạnh giá trị âm và chuỗi không parse được; các trường hợp
  này quay về local backoff.
- Bổ sung 4 regression cases trong `test_phase_1_litellm_client.py`; test
  contract riêng đạt **15 passed**.
- Xác minh toàn bộ suite đạt **290 passed, 2 skipped, 1 warning**; `compileall`
  thành công. Live smoke vẫn bị chặn bởi thiếu endpoint/credential thật.
- Chi tiết: `docs/ITERATION_12_RETRY_AFTER_FINITE_CONTRACT.md`.

### Iteration 14 — retry model request có idempotency key

- `ModelRequest` hiện có khóa idempotency tùy chọn, được validate và truyền qua
  header `Idempotency-Key`.
- `LiteLLMModelClient` chỉ retry theo `max_attempts` khi request có khóa; request
  không có khóa bị giới hạn một attempt. Các adapter model hiện hành tạo khóa
  ổn định từ correlation ID hoặc input nghiệp vụ.
- Chi tiết và lệnh kiểm chứng: `docs/ITERATION_14_IDEMPOTENT_MODEL_RETRY.md`.
- Xác minh iteration 14: **293 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` đều thành công. Live smoke vẫn chưa chạy do thiếu endpoint
  và credential thật.

### Iteration 15 — exponential retry backoff

- `LiteLLMModelClient` tăng delay local theo cấp số nhân giữa các lần retry;
  `Retry-After` hợp lệ vẫn được tôn trọng, còn giá trị không hợp lệ vẫn dùng
  local backoff.
- Bổ sung contract test cho chuỗi delay `1.5` rồi `3.0` giây.
- Xác minh iteration 15: **294 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` đều thành công. Live smoke vẫn bị chặn bởi endpoint và
  credential thật chưa được cung cấp.

### Iteration 54 — canonical identity của ChunkHit

- Siết `ChunkHit.source_ref`, `chunk_ref` và `retrieval_version` phải là chuỗi
  non-blank, không có whitespace ở đầu/cuối và Unicode NFC.
- Bổ sung 9 regression cases TDD cho whitespace và decomposed Unicode; targeted
  test **18 passed**.
- Chi tiết: `docs/ITERATION_54_CANONICAL_CHUNK_HIT_IDENTITY.md`.
- Live model-service smoke và production golden parity vẫn chưa xác minh do
  thiếu endpoint, credential và catalog production thật.

### Iteration 63 — canonical source row của Chroma

- Siết kết quả Chroma: `documents` phải là chuỗi và `metadatas` phải là
  mapping; provider response sai kiểu bị reject fail-closed tại adapter.
- Bổ sung regression tests cho hai dạng malformed source row.
- Xác minh: **394 passed, 2 skipped, 1 warning**; `compileall` và
  `git diff --check` thành công.
- Chi tiết: `docs/ITERATION_63_CHROMA_SOURCE_ROW_CONTRACT.md`.
- Live model-service smoke và production golden parity vẫn bị chặn do thiếu
  endpoint, credential và catalog production thật.
### Iteration 166 — bearer token không chứa control character

- `LiteLLMModelClient` reject bearer token có CR, LF, NUL hoặc control
  character trước khi tạo HTTP header; bổ sung 3 regression cases.
- Targeted test đạt **3 passed**; full suite, `compileall` và `git diff
  --check` được chạy sau thay đổi.
- Live model-service smoke và production parity vẫn bị chặn bởi thiếu
  endpoint, credential và catalog production thật.
- Chi tiết: `docs/ITERATION_166_MODEL_CLIENT_BEARER_TOKEN_CONTRACT.md`.
- Iteration 182: `RemoteGpuHealth` da co runtime guard cho status va
  capability (unique, non-blank, khong control character); targeted test **18
  passed**. Live model-service smoke va production parity van chua xac minh.

### Iteration 183 — dependency HTTP client của remote health

- `HttpRemoteGpuGateway` fail-fast neu `http_client.get` khong callable, tranh
  loi runtime muon trong `health()`.
- Regression test TDD da chung minh dependency sai bi tu choi tai constructor;
  chi tiet tai `docs/ITERATION_183_REMOTE_HEALTH_HTTP_CLIENT_CONTRACT.md`.
- Live model-service smoke va production parity van chua xac minh do checkout
  thieu endpoint, credential va production catalog.

### Iteration 191 — đồng bộ safe-path contract cho direct `AppSettings`

- `_validate_runtime_path` giờ từ chối parent traversal trên path tương đối,
  áp dụng nhất quán cho `data_root` và `chroma_persist_directory` cả khi
  settings được khởi tạo trực tiếp.
- Regression test TDD chứng minh trước sửa có **2 failed** và sau sửa phải
  chuyển xanh; bằng chứng chi tiết tại
  `docs/ITERATION_191_SETTINGS_DIRECT_PATH_TRAVERSAL.md`.
- Live model-service smoke và production golden parity vẫn chưa xác minh do
  checkout thiếu endpoint, credential và catalog production.

### Iteration 198 — safe-path contract cho tên thiết bị Windows

- `AppSettings` fail-closed khi `data_root` hoặc `chroma_persist_directory` có
  thành phần Windows device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`,
  `LPT1`-`LPT9`), kể cả tên có extension; contract áp dụng cho direct
  construction và environment parsing.
- Regression targeted: **20 passed**; chi tiết tại
  `docs/ITERATION_198_SETTINGS_WINDOWS_DEVICE_PATH_CONTRACT.md`.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout thiếu endpoint, credential và catalog production thật.
