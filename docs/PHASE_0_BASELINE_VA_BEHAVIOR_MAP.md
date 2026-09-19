# Phase 0 — baseline và bản đồ hành vi hiện tại

## Mục đích và phạm vi

Tài liệu này thực hiện lát cắt đầu tiên của Phase 0 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: khóa lại hành vi đang có trước khi
đổi cấu trúc source. Không có code production nào được di chuyển hoặc thay đổi
trong lát cắt này. Vì vậy, đây là ảnh chụp hiện trạng để các phase sau có thể
viết characterization/contract test đúng mục tiêu, thay vì refactor bằng niềm
tin và một ít cầu nguyện.

## Bằng chứng baseline

Lệnh chạy tại thư mục gốc repository vào ngày 20-09-2026:

```powershell
uv run pytest --basetemp=.pytest-tmp
```

Kết quả: **24 passed, 2 skipped trong 0.67s** (26 test được collect).

Hai test bị skip là có chủ đích của môi trường, không phải test thất bại:

| Test | Lý do skip ghi nhận bởi pytest | Tác động đến baseline |
|---|---|---|
| `tests/test_app.py` | Gradio chưa được cài | Không xác nhận được smoke test legacy UI trong dependency mặc định. |
| `tests/test_music_rag.py` | Không có sample source | Không xác nhận được case cần dữ liệu mẫu ngoài repository. |

Baseline này chỉ là offline unit/regression. Nó **không** xác minh GPU server,
OpenAI/DeepSeek, Chroma thật, upload PDF thật, hay browser UI.

## Bản đồ entrypoint và luồng đang có

| Bề mặt hiện tại | Entry point / bằng chứng source | Luồng quan sát được | Ranh giới đích theo kế hoạch |
|---|---|---|---|
| Legacy RAG UI | `app.py`: import `gradio`, `create_app()`, `main()` | Gradio tạo `ChromaChunkService`, `OpenAIEmbeddingProvider`, retrieval agent và answer agent để render kết quả/chát. | Không migrate UI; chỉ chuyển orchestration nghiệp vụ cần thiết sang backend FastAPI. |
| PDF layout web | `src/pdf_layout_web.py`: `app = FastAPI(...)` và các route `/api/jobs` | Upload PDF → ghi job JSON/artifact cục bộ → chạy extraction → client poll trạng thái/layout/page image. | Một FastAPI composition root, route chỉ gọi use case. |
| Extraction runtime | `pdf_layout_web._run_extraction()` import `extracted.parse_pdf_2_md` rồi gọi `check_gpu`, `create_source_coordinate_pipeline`, `save_one_pdf`. | Workload OCR/Paddle chạy cục bộ, được khởi động trong `threading.Thread(..., daemon=True)`. Job state nằm ở `runtime/pdf-layout-jobs/<job-id>/job.json`. | Backend CPU-only submit/poll remote GPU job; persist local/remote job mapping và recovery policy. |
| Chroma header-chunk | `music_rag.chroma_chunks.build_chroma_index()` và `search_chroma_chunks()` | Đọc header chunks/sidecar, gọi embedding provider, dùng `chromadb.PersistentClient`, ghi Chroma và `chunk-records.json`. | `KnowledgeRepository` là source of truth; Chroma chỉ là `VectorIndex` adapter, I/O blocking đi qua bounded executor. |
| Retrieval | `music_rag.chroma_service.ChromaChunkService` | Query Chroma, dựng candidate set trong memory (`_candidate_sets`), validate selection, trả source blocks/asset refs. | Retrieval facade tạo `EvidenceBundle` đã validate; không để chat hay route biết Chroma. |
| Answer | `music_rag.deepseek_answer.DeepSeekAnswerAgent` | Tạo OpenAI-compatible client và gửi source records cùng ảnh đã kiểm tra path tới DeepSeek. | `AnswerQuestion` chỉ nhận evidence đã validate; adapter remote GPU che giấu SDK/transport. |

## Storage và hợp đồng quan sát được

| Dữ liệu | Vị trí/cơ chế hiện tại | Nhận xét để giữ tương thích |
|---|---|---|
| Job extraction | `runtime/pdf-layout-jobs/<job-id>/job.json` | Có trạng thái và thời gian cục bộ, nhưng chưa có `remote_job_id`, idempotency key hoặc recovery sau restart. |
| Artifact extraction | Thư mục job: `source.pdf`, `pages/`, `extraction/` và layout JSON | Các artifact đang dựa trên filesystem cục bộ chung với backend; không được truyền nguyên local path qua boundary GPU mới. |
| Vector index | `runtime/chroma/...` qua Chroma persistent client | Index cần tiếp tục lưu vector, source `document` và metadata projection đã validate. |
| Source sidecar | `<chroma-dir>/chunk-records.json` | Hiện dùng để hydrate source và image metadata; cần được bọc bởi repository thay vì coi Chroma là nguồn duy nhất. |
| Legacy catalog | `CatalogStore` và các module `store/importer/manifest/search/semantic/service` | Là retrieval path song song; chưa quyết định xóa hay giữ compatibility adapter. |

## Điểm lệch có bằng chứng so với kiến trúc đích

1. Có hai web entrypoint: Gradio tại `app.py` và FastAPI tại
   `src/pdf_layout_web.py`; chưa có composition root chung.
2. `pdf_layout_web.py` vừa chứa HTTP route, inline HTML, filesystem persistence,
   subprocess rasterization, orchestration và local OCR/GPU import.
3. Extraction chạy trong daemon thread nên không có cơ chế resume/reconcile nếu
   process backend dừng giữa chừng.
4. `chroma_chunks.py` khởi tạo `chromadb.PersistentClient` và embedding provider
   trực tiếp; lời gọi này hiện là đồng bộ trong path application.
5. Các provider OpenAI/DeepSeek đọc environment và tạo client trong lớp nghiệp
   vụ hiện có; cấu hình và lifecycle chưa tập trung.
6. `ChromaChunkService` giữ candidate set trong memory; trạng thái này không
   bền qua restart và chưa phải evidence bundle có schema riêng.

## Quyết định chưa được tự giả định

Kế hoạch kiến trúc yêu cầu chốt các quyết định trước khi implementation phase
liên quan. Hiện repository chưa cung cấp bằng chứng để tự chọn các điểm sau:

1. Header chunks hay structured chunks là canonical ingestion input.
2. Legacy catalog phải giữ đến parity hay được deprecate.
3. Job/metadata repository sẽ tiếp tục JSON hay chuyển SQLite.
4. Pipeline tự chạy toàn bộ hay operator kích hoạt theo stage.
5. Chính sách resume job `running` sau restart.
6. API versioning và các endpoint compatibility cần giữ.

Vì các lựa chọn này thay đổi contract nghiệp vụ, iteration này không tự chọn
thay người vận hành. Lát cắt implementation tiếp theo an toàn là viết các
characterization test cho FastAPI job state và Chroma header-chunk contract,
sau khi các quyết định tương ứng được duyệt.

## Hành động kế tiếp đề xuất

1. Duyệt sáu quyết định ở trên bằng ADR hoặc acceptance tests.
2. Viết test characterization cho payload/status của job extraction hiện tại và
   record Chroma header-chunk/sidecar.
3. Chỉ sau khi test đỏ đã được duyệt, tạo Phase 1 package scaffold, typed
   settings và composition root tối thiểu.
