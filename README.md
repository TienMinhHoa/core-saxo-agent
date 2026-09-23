# Saxophone RAG Backend

`saxophone-rag-backend` là backend FastAPI modular monolith cho extraction PDF,
ingestion, retrieval và chat dựa trên evidence. Entrypoint duy nhất là
`saxophone-api`.

## Bootstrap va chay nhanh bang Bash

Tren Linux hoac WSL, sau khi clone repository:

```bash
bash bin/run_app.sh
```

Script se tu tim hoac cai `uv`, cai Python 3.12, dong bo dependency theo
`uv.lock` (bao gom extra `paddle-client`), tao `.env` tu `.env.example` neu
chua co, roi chay API tren `0.0.0.0:8000`.

Co the doi dia chi bind bang bien moi truong:

```bash
SAXO_HOST=127.0.0.1 SAXO_PORT=8000 bash bin/run_app.sh
```

Neu `.env` vua duoc tao tu template, hay dien credential/model service truoc
khi su dung cac endpoint can LLM.

## Kiến trúc

- `saxophone.documents`: định danh document, artifact và metadata source.
- `saxophone.extraction`: gọi external model service để trích xuất PDF.
- `saxophone.ingestion`: chunk, tagging, embedding và index Chroma.
- `saxophone.retrieval`: `ChunkRetriever` và `EvidenceBundle` đã validate.
- `saxophone.chat`: tổng hợp câu trả lời từ evidence đã kiểm chứng.
- `saxophone.interfaces`: FastAPI routes; không gọi provider SDK trực tiếp.

GPU inference cho VLM/embedding/LLM chạy ở service bên ngoài. Riêng PDF
layout dùng PaddleOCR-VL client: layout detection chạy bằng CPU tại backend,
còn VL recognition được gửi tới vLLM server. Backend không dùng CUDA/GPU.

## Chạy backend

`saxophone-api` tự đọc file `.env` tại thư mục đang chạy và giữ ưu tiên cho
biến môi trường đã có trong process. Có thể cấu hình trong `.env` hoặc đặt tối
thiểu các biến sau cho phiên PowerShell hiện tại:

```powershell
$env:SAXO_REMOTE_GPU_BASE_URL = "https://model-service.example.com"
$env:SAXO_REMOTE_GPU_BEARER_TOKEN = "<token-cua-ban>"
$env:SAXO_LITELLM_ENDPOINT = "https://model-service.example.com/v1/invoke"
$env:SAXO_PADDLE_VLLM_SERVER_URL = "http://<ip-server-gpu>:8000/v1"
```

Nếu mới chỉ cần PDF layout và chưa cấu hình AI/LiteLLM service chung, chạy:

```powershell
$env:SAXO_PADDLE_VLLM_SERVER_URL = "http://<ip-server-gpu>:8000/v1"
uv sync --extra paddle-client
uv run saxophone-api --layout-only --host 127.0.0.1 --port 8080
```

Mở `http://127.0.0.1:8080/pdf-layout/`. Chế độ này không yêu cầu
`SAXO_REMOTE_GPU_BASE_URL`, nên lỗi cấu hình bạn gặp trước đó sẽ không còn.

Khi chạy đầy đủ RAG/search/chat, xem `.env.example` để biết toàn bộ cấu hình rồi
chạy:

```bash
uv sync --extra paddle-client
uv run saxophone-api --host 127.0.0.1 --port 8000
```

Để bật full luồng topic tagging mới, cấu hình thêm:

```dotenv
SAXO_CHUNK_TAGGING_ENABLED=true
SAXO_LITELLM_STRUCTURED_OUTPUT_MODE=json_schema
```

Nếu muốn gọi thẳng API chính chủ DeepSeek và OpenAI, không qua gateway:

```dotenv
SAXO_MODEL_PROVIDER=direct
DEEPSEEK_API_KEY=<deepseek-key>
OPENAI_API_KEY=<openai-key>
SAXO_DEEPSEEK_MODEL=deepseek-flash
SAXO_AGENT_CHAT_MODEL=deepseek-pro
SAXO_DEEPSEEK_REASONING_EFFORT=max
SAXO_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
SAXO_CHUNK_TAGGING_ENABLED=true
SAXO_LITELLM_STRUCTURED_OUTPUT_MODE=json_object
```

Sau khi ingest tai lieu, mo giao dien chat tai:

```text
http://127.0.0.1:8000/agent/chat
```

Trang nay dung full topic retrieval flow da cau hinh. Buoc sinh cau tra loi dung
`SAXO_AGENT_CHAT_MODEL`; tagging va role selection van giu model rieng cua pipeline.

Ước lượng `output_v3/input-vl` mà chưa gọi API:

```powershell
uv run python -m saxophone.cli.topic_input_vl
```

Pilot 5 chunk rồi mới chạy full:

```powershell
uv run python -m saxophone.cli.topic_input_vl --limit 5 --document-ref music-theory-pilot --execute
uv run python -m saxophone.cli.topic_input_vl --document-ref music-theory-full --execute
```

Để dừng sau khi gán tag, tạo embedding và ghi vector index mà không retrieval
hoặc sinh câu trả lời, thêm `--ingest-only`:

```powershell
uv run python -m saxophone.cli.topic_input_vl --limit 5 --document-ref music-theory-pilot --ingest-only --execute
uv run python -m saxophone.cli.topic_input_vl --document-ref music-theory-full --ingest-only --execute
```

Mỗi lần gọi DeepSeek/OpenAI sẽ ghi token input, token output và chi phí USD ước
tính vào `logs/YYYY-MM-DD.log`. Logger không ghi prompt, response hay API key.

Trong lúc ingest, terminal và cùng file log sẽ hiển thị tiến trình theo từng
chunk và stage. Ví dụ:

```text
[INGEST] stage=tagging status=started chunk=12/315 completed=11/315 progress=3.49% elapsed=420.5s eta=11620.2s
[INGEST] stage=tagging status=completed chunk=12/315 completed=12/315 progress=3.81% elapsed=451.8s eta=11407.9s
[INGEST] stage=embedding status=started completed=315/315 progress=100.00% elapsed=10842.0s eta=n/a
```

Các stage sau tagging gồm `concept_catalog`, `embedding`, `content_ledger`,
`vector_plan`, `persistence`, `index_publish`, `vector_sync` và `completed`.
ETA chỉ là ước lượng dựa trên tốc độ các chunk đã hoàn thành; thời gian suy luận
của từng chunk có thể chênh lệch đáng kể.

Khi cờ này bật và Chroma khả dụng, composition root tạo sẵn
`app.state.container.extract_topic`. Facade nội bộ này chạy được chuỗi:

```text
Markdown/header chunks -> paragraph tagging -> SQLite/outbox
-> chunk + concept vectors -> question retrieval -> grounded answer
```

Không có endpoint topic-tagging mới; đây là chủ ý của phạm vi service-first.
Ví dụ Python chạy trực tiếp, hướng dẫn re-ingestion/outbox và quyền sở hữu dữ
liệu nằm trong `docs/TOPIC_TAGGING_RUNBOOK.md`.

Trên máy GPU, khởi động VLM server riêng:

```bash
vllm serve PaddlePaddle/PaddleOCR-VL --trust-remote-code --max-num-batched-tokens 16384 --port 8000
```

`SAXO_PADDLE_VLLM_SERVER_URL` phải là URL mà máy backend truy cập được;
không dùng `localhost` nếu vLLM chạy trên máy khác. Lưu ý:
`vl_rec_backend="vllm-server"` chỉ remote phần VL recognition; PaddleOCR client
vẫn chạy layout stage trên CPU backend.

Mở `http://127.0.0.1:8000/docs` để xem API và gọi
`http://127.0.0.1:8000/api/v1/health` để kiểm tra model service.
Mở `http://127.0.0.1:8000/pdf-layout/` để upload PDF, chạy PaddleOCR-VL
và xem layout box.

## Kiểm thử offline

```bash
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Các lệnh này kiểm chứng contract và behavior offline. Chúng không thay thế live
smoke với endpoint, credential và catalog production đã được phê duyệt.

## Tài liệu

- `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: kiến trúc và migration plan.
- `docs/REFACTOR_ACCEPTANCE_STATUS.md`: bằng chứng acceptance offline/live.
- `docs/LIVE_MODEL_SERVICE_SMOKE_STATUS.md`: trạng thái live smoke tách riêng.
- `docs/TOPIC_TAGGING_RUNBOOK.md`: chạy ingest/tag/retrieve/answer không qua HTTP.
- `docs/TOPIC_TAGGING_IMPLEMENTATION_STATUS.md`: đối chiếu implementation hiện tại.
## Quy trinh ingest de copy/paste

Chay cac lenh sau tu thu muc goc cua repository. `--execute` moi bat dau goi
DeepSeek/OpenAI va co the phat sinh chi phi; bo `--execute` chi xem uoc luong.

### 1. Chuan bi moi truong

Windows PowerShell:

```powershell
uv sync
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
notepad .env
```

Linux/VPS:

```bash
uv sync --locked
cp -n .env.example .env
nano .env
```

Voi direct DeepSeek/OpenAI, `.env` toi thieu can co:

```dotenv
SAXO_MODEL_PROVIDER=direct
DEEPSEEK_API_KEY=<deepseek-key>
OPENAI_API_KEY=<openai-key>
SAXO_DEEPSEEK_MODEL=<model-duoc-api-deepseek-cap-phep>
SAXO_AGENT_CHAT_MODEL=<model-dung-cho-chat>
SAXO_CHUNK_TAGGING_ENABLED=true
SAXO_LITELLM_STRUCTURED_OUTPUT_MODE=json_object
```

Khong commit `.env`, API key, `runtime/`, `logs/` hoac database SQLite len Git.

### 2. Kiem tra dau vao va uoc luong token

Lenh nay doc du lieu da co trong `output_v3/input-vl`, khong goi LLM:

```powershell
uv run python -m saxophone.cli.topic_input_vl --document-ref music-theory-pilot --limit 5
```

Output phai cho biet `chunks`, `paragraphs` va
`approximate_tagging_input_tokens`. Day la uoc luong input; output/thinking
tokens va chi phi thuc te phu thuoc provider.

### 3. Chay pilot 5 chunk

Nen chay pilot truoc de kiem tra credential, model, JSON output va vector store:

```powershell
uv run python -m saxophone.cli.topic_input_vl --limit 5 --document-ref music-theory-pilot --ingest-only --execute
```

Thanh cong khi report co `failed_paragraph_count=0`, `indexed=true`,
`errors=[]` va `vector_sync_failed=0`.

### 4. Chay full ingest

Sau khi pilot thanh cong:

```powershell
uv run python -m saxophone.cli.topic_input_vl --document-ref music-theory-full --ingest-only --execute
```

Neu muon chay them cau hoi smoke test sau ingest, bo `--ingest-only` va them
`--question`.

### 5. Doc log tien trinh va cache

Tien trinh duoc in ra terminal va ghi vao `logs/YYYY-MM-DD.log`:

```text
[INGEST] stage=tagging status=reused chunk=1/315 completed=1/315
[INGEST] stage=tagging status=completed chunk=6/315 completed=6/315
[INGEST] stage=tagging status=warning chunk=6/315 completed=5/315
```

- `status=reused`: chunk da co ket qua tagging trong content cache (SHA/MD5),
  khong can goi LLM lai.
- `status=completed`: chunk da tag, embed, persist SQLite/content cache va sync
  vector Chroma thanh cong. Pipeline chi bat dau chunk tiep theo sau checkpoint nay.
- `status=warning` roi `completed`: reservation `processing` cu het han 60
  phut, duoc thu hoi va xu ly lai.
- `status=warning` ma khong co `completed`: chunk dang duoc tien trinh khac
  xu ly va bi bo qua de tranh inject trung.
- `failed`: chunk that bai; xem `errors` va log provider de retry.

Cache tagging va cache embedding la hai lop khac nhau. Cache embedding duoc
bao cao bang `reused_embedding_count` trong report cuoi.

Ingest full duoc checkpoint theo tung chunk. Neu process dung sau chunk 153,
lan chay lai se reuse cac chunk da `completed` va tiep tuc phan con lai. Concept
catalog va stale-vector cleanup van duoc tong hop/finalize sau khi tat ca chunk
da checkpoint thanh cong.

### 6. Kiem tra sau ingest

Windows PowerShell:

```powershell
Get-ChildItem logs
Get-Content (Get-ChildItem logs -Filter '*.log' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName -Tail 80
```

Linux/VPS:

```bash
tail -n 80 "logs/$(date +%F).log"
```

Chi coi la ingest san sang khi `indexed=true`, `errors=[]` va
`vector_sync_failed=0`. Neu co `vector sync failed`, tagging co the da xong
nhung vector index chua dong bo day du.

## Xem du lieu ChromaDB

Sau khi backend dang chay, mo giao dien read-only:

```text
http://127.0.0.1:8000/db
```

Giao dien cho phep chon collection, tim trong document text, loc theo
`document_ref`, phan trang va xem metadata. Endpoint khong tra embedding vector
va khong co thao tac sua/xoa du lieu. Neu deploy cong khai tren VPS, can bao ve
route `/db` o reverse proxy vi metadata va noi dung tai lieu co the nhay cam.
