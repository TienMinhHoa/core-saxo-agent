# Cách LLM hoạt động trong codebase

File này là bản đồ để kiểm tra các lần gọi AI của Saxophone. File chỉ mang tính tài liệu, runtime không đọc file này như prompt hay config.

## Provider và cấu hình

`src/saxophone/app/settings.py` đọc và kiểm tra `.env`; `src/saxophone/app/factory.py` chọn provider:

| Chế độ | Adapter | Nơi nhận request | Ghi chú |
| --- | --- | --- | --- |
| `gateway` (mặc định) | `LiteLLMModelClient` | `SAXO_LITELLM_ENDPOINT` (mặc định `<SAXO_REMOTE_GPU_BASE_URL>/v1/invoke`) | Dùng `SAXO_REMOTE_GPU_BEARER_TOKEN`; gateway định tuyến các model task. |
| `direct` | `DirectApiModelClient` | DeepSeek chat completions và OpenAI embeddings | Cần `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `SAXO_CHUNK_TAGGING_ENABLED=true`, `SAXO_LITELLM_STRUCTURED_OUTPUT_MODE=json_object`. Không hỗ trợ `pdf_extract` qua adapter này. |
| PDF layout UI | PaddleOCR client + vLLM | `SAXO_PADDLE_VLLM_SERVER_URL` | Pipeline riêng; layout chạy CPU local, recognition chạy remote. |

Trong topic pipeline:

- `SAXO_DEEPSEEK_MODEL` là model text của direct adapter.
- `SAXO_AGENT_CHAT_MODEL` dành riêng cho bước answer tại `/agent/chat`.
- `SAXO_OPENAI_EMBEDDING_MODEL` và `SAXO_EMBEDDING_DIMENSION` phải khớp collection Chroma.
- Với gateway, `SAXO_LITELLM_MODEL_PROFILE` được gửi trong `ModelRequest`; gateway map profile này sang model thật.

## LLM được gọi ở đâu?

| Giai đoạn | Code chính | Input -> output |
| --- | --- | --- |
| PDF extraction (gateway) | `extraction/remote.py` | Artifact PDF -> Markdown, layout và manifest refs. |
| Legacy paragraph tagging | `tagging/adapters.py` | Paragraph -> tag và quyết định xử lý xung đột. |
| Topic chunk tagging | `tagging/structured_chunk.py` | Chunk, paragraph và context -> concept, role và conflict decision đã validate. |
| Embedding | `ingestion/adapters.py` | Text chunk/concept/câu hỏi -> vector qua OpenAI (direct) hoặc gateway. |
| Retrieval selection | `retrieval/paragraph_selection.py` | Câu hỏi + paragraph choices -> các paragraph được chọn. |
| Grounded answer | `chat/service.py` | Context Markdown đã giới hạn -> JSON answer + used refs; ref phải thuộc context. |
| Agent document search | `agent/document_search.py` | `AgentQuestion` -> semantic chunk hits, hydrated paragraph/concept-role candidates, pages, images và confidence. |
| Agent web fallback | `agent/web_search.py` | `AgentQuestion` -> bounded, normalized web results trong shared `RunBudget`. |
| Agent synthesis | `agent/synthesis.py` | Immutable `EvidenceLedger` -> LangChain structured answer, citations và cited image evidence. |

`RemoteStructuredLlmProvider` trong `tagging/structured_provider.py` tạo `ModelRequest` với schema và task type, gọi `ModelClient.invoke`, kiểm tra task/response schema rồi validate output typed.

- `json_schema`: gửi schema structured output cho provider.
- `json_object`: đưa schema vào prompt và validate sau khi nhận response.
- Gateway kiểm tra identity của response.
- Direct adapter parse JSON từ DeepSeek và kiểm tra dimension, số lượng vector từ OpenAI.
- Timeout/retry dùng `SAXO_LITELLM_TIMEOUT_SECONDS`, `SAXO_LITELLM_MAX_ATTEMPTS`, `SAXO_LITELLM_RETRY_BACKOFF_SECONDS`.
- Token, model event và chi phí ước tính được ghi vào `logs/YYYY-MM-DD.log`; API key không được ghi vào log.

## Cách kiểm tra

1. Copy `.env.example` thành `.env`, điền credential/URL thật và chọn `gateway` hoặc `direct`. Không commit `.env`.
2. Kiểm tra offline bằng `uv run pytest -q`. Các fake provider và HTTP mock kiểm tra contract mà không gọi model thật.
3. Chạy `uv run saxophone-api --host 127.0.0.1 --port 8000`, sau đó gọi `GET /api/v1/health`. Endpoint này kiểm tra trạng thái model service nhưng không tự gửi prompt.
4. Kiểm tra topic ingest an toàn bằng `uv run python -m saxophone.cli.topic_input_vl --source <đường-dẫn-json> --limit 5`. Lệnh mặc định chỉ ước lượng. Thêm `--ingest-only --execute` để gọi provider, tag/embed/index 5 chunk; kiểm tra `indexed=true`, `errors=[]`, `vector_sync_failed=0` trong report và log.
5. Sau khi có dữ liệu, gọi `POST /agent/chat/messages` với `{"question":"What is a major triad?"}` để kiểm tra compatibility retrieval -> selection -> answer và `sources`.
6. Nếu composition root được inject `AgentGraphDependencies`, gọi `POST /agent/chat/stream` để kiểm tra Main Agent LangGraph, event stage/tool/completion và replay bằng `X-Agent-Run-ID`/`Last-Event-ID`.

Nếu không có hit hoặc paragraph phù hợp, compatibility service trả status tương ứng và không sinh answer. Main Agent trả outcome typed như `answered`, `needs_clarification`, `insufficient_evidence`, `budget_exhausted` hoặc `failed`; synthesis chỉ được nhận evidence đã validate trong ledger. `/api/v1/health` và `/api/v1/chat` không dùng chung wiring với `/agent/chat/messages`; route chat cũ có thể trả 503 dù topic chat đã sẵn sàng. Trong `direct` mode, PDF `process` không được wire mặc định; dùng `/pdf-layout/` cho pipeline Paddle riêng.

## Main Agent, streaming và tracing

`MainAgent` trong `agent/orchestrator.py` chạy graph đã compile từ
`langgraph.graph.StateGraph`. Các node search, selection, web fallback,
clarification, synthesis và validation chỉ trao đổi DTO typed qua
`AgentGraphState`; graph không để state raw đi thẳng ra API.

`POST /agent/chat/stream` phát các event allowlist như `run_started`,
`stage_started`, `tool_started`, `tool_completed`, `decision`,
`synthesis_started`, `answer_delta`, `run_completed` và `run_failed`. Event
không chứa prompt đầy đủ, hidden reasoning, raw provider output hoặc secret.
`AgentRunManager` lưu sequence để client reconnect và replay từ
`Last-Event-ID`; disconnect sẽ cancel run đang hoạt động.

`AgentTracer` tạo trace và observation parent-child cho graph, tool và model.
`create_langfuse_tracer` chỉ bật adapter Langfuse khi `LANGFUSE_*` được cấu
hình; payload được redact ở agent boundary và tracer no-op không thay đổi
behavior khi tắt.
