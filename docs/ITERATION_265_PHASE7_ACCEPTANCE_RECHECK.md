# Iteration 265 — rà soát nghiệm thu Phase 7

## Phạm vi

Iteration này rà soát nhỏ sau khi inbound API đã chuyển sang public facade ở
Iteration 264. Phạm vi không mở rộng sang live provider hoặc deployment; mục tiêu
là bảo đảm các ràng buộc dependency của Phase 7 vẫn được kiểm chứng tự động.

## Kết quả

- `interfaces/api.py` chỉ nhận contract từ các facade `chat`, `documents`,
  `extraction`, `ingestion`, `retrieval` và `workflows`.
- Các module nghiệp vụ không import ngược `interfaces`, `app` hoặc `main`.
- Các adapter task-specific vẫn đi qua `LiteLLMModelClient`; HTTP transport chỉ
  nằm ở `platform` hoặc composition root.
- Domain models/ports không phụ thuộc FastAPI, provider SDK, GPU runtime hoặc
  dotenv.
- Contract job lifecycle cũ (`WorkflowJob`, `JobStatus`, `JobRepository`,
  `JobExecutor`, `remote_job_id`, submit/poll) không xuất hiện trong source
  backend hiện tại.

## Bằng chứng kiểm tra

Các lệnh được chạy trong checkout này:

```text
uv run pytest tests/test_phase_7_dependency_enforcement.py
uv run pytest
uv run python -m compileall -q src tests
git diff --check
```

Kết quả thực tế: targeted dependency enforcement **27 passed**; full offline
suite **948 passed, 18 skipped, 1 warning**; `compileall` và `git diff --check`
đều đạt.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa thể xác minh vì
checkout không có endpoint, credential và production catalog thật. Đây là
blocker môi trường, không phải lý do để thêm fallback local GPU/model runtime
vào backend.
