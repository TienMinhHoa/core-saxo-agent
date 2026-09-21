# Saxophone RAG Backend

`saxophone-rag-backend` là backend FastAPI modular monolith cho extraction PDF,
ingestion, retrieval và chat dựa trên evidence. Entrypoint duy nhất là
`saxophone-api`.

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

`saxophone-api` đọc biến môi trường của process; nó không tự động đọc file
`.env`. Trong PowerShell, đặt tối thiểu các biến sau cho phiên hiện tại:

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
