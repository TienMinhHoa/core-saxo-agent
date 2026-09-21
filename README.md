# Music Theory Source RAG

Backend web chính là `saxophone-api`, phục vụ các workflow PDF/extraction của
modular monolith. Gradio app chỉ là compatibility UI legacy cho luồng:
**câu hỏi → semantic retrieval → chọn content item → trả toàn bộ source block và ảnh**;
ứng dụng này không thuộc runtime backend mặc định và không dùng LLM để viết một câu
trả lời mới từ sách.

## Trạng thái demo hiện tại

Catalog của `Music Theory For Dummies` đã được tạo trong `runtime/music-theory-demo`:

- 4.082 source block, 405 asset đã checksum;
- 17 chapter item lấy theo heading `Chapter` của nguồn;
- mọi chapter đang là `needs_review`, nên chưa thể search hoặc hiển thị public.

Đây là chủ ý: chỉ người vận hành mới có thể xác nhận ranh giới source và chuyển item sang `approved`.

## Thiết lập

Project dùng Python 3.12 và `uv`; `pyproject.toml` cùng `uv.lock` là nguồn chuẩn
cho dependency. Cài môi trường backend và dependency phát triển:

```bash
uv sync
```

Gradio chỉ còn là legacy UI, không thuộc runtime backend mặc định. Chỉ cài khi
cần chạy `app.py` cũ:

```bash
uv sync --extra legacy-ui
```

Entrypoint backend FastAPI chính là `saxophone-api`; lệnh này dùng factory
`saxophone.main:create_application` để tạo một app duy nhất và không khởi động
Gradio:

```bash
uv run saxophone-api --host 127.0.0.1 --port 8000
```

Môi trường mặc định không cài Paddle, CUDA hoặc model GPU. Các workload cần GPU
sẽ được chuyển sang remote GPU server theo tài liệu kiến trúc; các script local
Paddle hiện tại được xem là legacy cho đến khi có remote adapter.

Cấu hình nằm trong `.env`; điền API key server-side:

```dotenv
OPENAI_API_KEY=...
MUSIC_RAG_EMBEDDING_MODEL=text-embedding-3-small
MUSIC_RAG_AGENT_MODEL=gpt-4.1-mini
MUSIC_RAG_MAX_ROUNDS=4
MUSIC_RAG_CATALOG=runtime/music-theory-demo
MUSIC_RAG_ACCESS_SCOPE=public
GRADIO_SERVER_NAME=0.0.0.0
GRADIO_SERVER_PORT=7860
GRADIO_SHARE=true
```

Không commit hoặc gửi file `.env`. API key chỉ được backend gọi OpenAI embeddings, không được gửi tới trình duyệt.

## Publish demo sau khi operator duyệt

1. Kiểm tra file `runtime/music-theory-review-manifest.json`. Nó khai báo chapter, danh sách source block và trạng thái duyệt.

2. Khi bạn xác nhận các chapter boundary này phù hợp để dùng làm demo, chạy lệnh sau. Cờ `--operator-approves` là xác nhận có chủ đích; không chạy nó nếu chưa duyệt.

```bash
uv run music-rag \
  --catalog runtime/music-theory-demo \
  bootstrap-music-theory-demo \
  "output/Music Theory For Dummies/Music Theory For Dummies.md" \
  --asset-root "output/Music Theory For Dummies" \
  --manifest-output runtime/music-theory-review-manifest.json \
  --operator-approves
```

3. Xây keyword index và semantic index. Semantic index gọi OpenAI embeddings một lần cho các source search chunk; model phải trùng với `MUSIC_RAG_EMBEDDING_MODEL` khi chạy app.

```bash
uv run music-rag \
  --catalog runtime/music-theory-demo build-index

uv run music-rag \
  --catalog runtime/music-theory-demo build-semantic-index
```

4. Khởi động (hoặc restart) Gradio:

```bash
uv run --extra legacy-ui python app.py \
  --catalog runtime/music-theory-demo \
  --access-scope public \
  --host 0.0.0.0 \
  --port 7860 \
  --share
```

Nếu port `7860` đã có phiên bản cũ đang chạy, dừng phiên bản đó trong terminal trước, hoặc chạy phiên bản test mới trên port khác, ví dụ `--port 7861`.

Gradio in URL `gradio.live` ra terminal; đây là link test tạm thời và hết hạn sau khoảng một tuần.

## Kiểm thử

```bash
uv run pytest
```

Test gồm parser/asset validation, review state, dependency/version/scope, renderer không synthesis, semantic retrieval với fake embeddings, và Gradio smoke test.

## PDF layout extractor

Backend ch盻・cung c蘯･p m盻冢t web entrypoint `saxophone-api`. OCR/PP-StructureV3
ch蘯｡y trﾃｪn model service remote; backend khﾃｴng cﾃi Paddle, CUDA ho蘯ｷc
model weight local. Tham s盻・`device` trong workflow ch盻・lﾃ profile tﾆｰﾆ｡ng
thﾃｭch, khﾃｴng ph蘯｣i b蘯ｱng ch盻ｩng backend cﾃｳ GPU local.

Viewer cục bộ cho luồng **tải PDF → chạy PP-StructureV3 → đối chiếu bounding
box với text/ảnh trích xuất**. Khởi động bằng virtual environment của project:

```bash
uv run saxophone-api --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`, chọn PDF, bấm **Thêm tài liệu**, rồi bấm **Chạy
extract**. Chọn `GPU 0` nếu CUDA đã được expose; nếu không dùng `CPU`.

Kết quả job được giữ ở `runtime/pdf-layout-jobs/<job-id>/`: PDF gốc, PNG của
từng trang, Markdown/ảnh OCR, và `extraction/source/layout/page-XXXX.json`.
Viewer dùng `parsing_res_list[].block_content` và `source_bbox` trong các file
này để liên kết block bên phải với khung trên trang. `source_bbox` chỉ được
ghi khi OCR chạy trên raster PDF gốc, không rotate hay unwarp; JSON khai báo
`coordinate_space: raw_pdf_raster_pixels` với gốc ở góc trên-trái. Cần `pdftoppm` từ
`poppler-utils` để rasterize trang PDF cho viewer.

## Figure enrichment với DeepSeek Flash Vision

Sau khi chạy PaddleOCR-VL, tạo map caption theo bbox và kiểm tra request trước
khi gọi VLM:

```bash
uv run python -m extracted.map_paddle_vl_captions output/input-vl
uv run python -m extracted.analyze_paddle_vl_figures output/input-vl --plan-only
```

Điền `DEEPSEEK_API_KEY` vào `.env`, rồi chạy VLM. Pipeline gửi cả caption đã
map bằng heuristic lẫn ảnh chưa map; kết quả được append nên có thể resume:

```bash
uv run python -m extracted.analyze_paddle_vl_figures \
  output/input-vl --max-figures 5 --workers 4
```

Sau khi xem năm kết quả đầu, bỏ `--max-figures` để xử lý phần còn lại. Mặc định
là bốn request đồng thời; chỉnh `--workers` hoặc `FIGURE_VLM_WORKERS` nếu cần.
Kết quả nằm tại `output/input-vl/vlm-figures/figure-vlm-results.jsonl`; log text
cuối lượt với tổng token và tổng chi phí nằm tại
`output/input-vl/vlm-figures/figure-vlm-run.log`.

Để xem ảnh bên trái và caption/tóm tắt tương ứng bên phải, render thành
Markdown:

```bash
uv run python -m extracted.render_vlm_figures_markdown \
  output/input-vl
```

File tạo ra là `output/input-vl/vlm-figures/figure-review.md`. Dùng
`--only-valid` nếu chỉ muốn xem các asset mà VLM xác nhận là figure hợp lệ.

Để chia Markdown thành các chunk theo header, có page range trong JSON và bản
Markdown để kiểm tra:

```bash
uv run python -m extracted.extract_header_chunks \
  output/input-vl/document.md
```

Lệnh này cũng tự đọc `output/input-vl/vlm-figures/figure-vlm-results.jsonl`, chèn
caption/tiêu đề/mô tả VLM ngay sau từng ảnh tương ứng trong bản Markdown, và bỏ
qua các ảnh có kết quả `No valid content`. Dùng `--vlm-results PATH` nếu file VLM
nằm ở chỗ khác; thêm `--keep-no-valid` nếu muốn giữ các ảnh bị loại.

Mặc định parser lấy header cấp 2 (`##`). Có thể đổi cấp bằng
`--heading-level`; output mặc định là `document-header-chunks.json` và
`document-header-chunks.md` cạnh file nguồn.

### Sửa hierarchy OCR bằng DeepSeek Flash

Pipeline này chỉ cho LLM gán vai trò heading; việc dựng Part/Chapter/Section,
giữ thứ tự nguồn, page range và nội dung được thực hiện bằng code. Vì vậy các
header cùng tên ở vị trí không liên tục không bị merge. Bản Markdown cuối giữ
ảnh và chèn caption/summary đã có trong `vlm-figures/figure-vlm-results.jsonl`.

Ước lượng token/chi phí mà không gọi API:

```bash
uv run python -m extracted.structure_markdown_with_llm \
  output/input-vl/document.md --estimate-only
```

Chạy toàn bộ tài liệu bằng `deepseek-flash`, thinking `max` (tự resume từ
`document-structure-labels.json` nếu bị gián đoạn):

```bash
uv run python -m extracted.structure_markdown_with_llm \
  output/input-vl/document.md
```

Đầu ra chính là `output/input-vl/document-structured.md`. Các file JSON đi kèm
lưu nhãn LLM, cây hierarchy, continuous chunks và usage/chi phí thực tế.

## Hành vi khi người dùng đặt câu hỏi

1. Hai tab đều embed câu hỏi và search collection Chroma bằng cosine similarity.
2. Agent retrieval xem tối đa ba candidate, chỉ chọn source ID hoặc yêu cầu retry; không sinh answer ở bước này.
3. Nếu chưa phù hợp, agent rewrite query theo khía cạnh mới rồi search lại; `MUSIC_RAG_MAX_ROUNDS` tối đa 4 vòng.
4. Tab Header trả source chunk và ảnh VLM; tab Answer gửi source được chọn cùng các candidate gần nhất cho DeepSeek Flash để tổng hợp.
5. Ảnh luôn được kiểm tra path/allow-list trước khi Gradio render.

### Chạy giao diện Chroma/VLM

`app.py` có thêm tab **Header Chroma/VLM RAG**. Tab này giữ agentic flow của
catalog cũ (candidate → agent đánh giá → rewrite/retry tối đa 4 vòng), nhưng
semantic retrieval dùng collection `MUSIC_RAG_CHROMA_COLLECTION`; source được
trả từ sidecar cùng Gallery các ảnh VLM hợp lệ kèm figure/caption/summary.

```bash
uv run --extra legacy-ui python app.py \
  --chroma-dir runtime/chroma/music-theory-for-dummies
```

Các file ảnh trong Chroma sidecar được đưa vào Gradio allow-list theo đúng
`extraction_dir`, không mở cả thư mục nguồn.

Tab **Answer RAG · DeepSeek Flash** chạy cùng agentic retrieval, sau đó gửi
source chunks (kèm figure metadata và tối đa số ảnh theo cấu hình) cho DeepSeek
Flash để tổng hợp. Thinking được bật bằng `extra_body.thinking=enabled` và
`reasoning_effort=high`; reasoning nội bộ không render ra UI. Tab hiển thị
riêng input/output/reasoning token và chi phí của request tổng hợp, không cộng
chi phí embedding hay candidate-selection.

## Chroma index cho header chunks

Header chunks từ Paddle/VLM có thể được lập một index ChromaDB riêng, không làm
thay đổi luồng search/catalog hiện tại:

```bash
uv run python -m music_rag.chroma_chunks \
  output/input-vl/document-header-chunks.json \
  --extraction-dir output/input-vl \
  --persist-dir runtime/chroma/music-theory-for-dummies
```

Có thể điều chỉnh tốc độ bằng `--workers N` (mặc định 4) và `--batch-size N`;
progress được in theo số chunk đã embed. Dùng `--no-progress` cho log máy.
Nếu gặp `429/rate_limit`, giảm `--workers` xuống 1–2; các batch đã hoàn tất
được giữ lại nên có thể chạy lại để tiếp tục.

Chunk vượt giới hạn input của embedding sẽ được bỏ qua trước khi gọi API (mặc
định guard 8.000 token, đặt lại bằng `--max-input-tokens`). Các chunk bị bỏ qua
được in ra theo `chunk_index/header/page` và ghi trong
`index-report.json` dưới `skipped_oversized_chunks`; chúng không tạo vector và
không phát sinh chi phí.

Embedding request chỉ nhận `header + content` sau khi bỏ markup ảnh và block
caption HTML. Chroma giữ vector và metadata; `chunk-records.json` giữ nguyên
chunk cùng các ảnh được VLM xác nhận hợp lệ. `ChromaChunkService` bọc kết quả
Chroma thành candidate/source-block contract để dùng chung với
`AgenticRetriever`; `MusicMaterialService` và tab Catalog RAG cũ vẫn giữ nguyên.

Để kiểm tra chi phí trước khi chạy toàn bộ, dùng `--max-chunks 2` với một
`--persist-dir` tạm thời. Báo cáo token/chi phí được ghi ở
`<persist-dir>/index-report.json`; các lần chạy lại chỉ embed chunk mới hoặc
đã thay đổi.
