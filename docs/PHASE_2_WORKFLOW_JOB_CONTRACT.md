# Phase 2 — workflow boundary

## Mục tiêu lát cắt

Theo hướng Clean Code hiện hành trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`,
workflow target gọi model service trực tiếp qua port typed. Backend không sở hữu
submit/poll lifecycle và không lưu trạng thái job của provider.

## Thay đổi

- `saxophone.workflows` chỉ công khai các use case xử lý tài liệu và ingestion.
- Task type, request/response schema, timeout, retry và circuit breaker nằm ở
  `saxophone.platform.model_client.LiteLLMModelClient` cùng adapter nhiệm vụ.
- Đã loại bỏ DTO `WorkflowJob`, `JobStatus`, `remote_job_id` và export tương ứng
  vì chúng mô tả kiến trúc submit/poll đã bị thay thế.

## Bằng chứng kiểm chứng

Lệnh chạy:

```powershell
uv run pytest -q tests/test_phase_1_litellm_client.py tests/test_phase_3_process_document.py --basetemp=.pytest-tmp
```

Các test xác minh request/response typed trực tiếp, retry/circuit policy và
workflow xử lý artifact qua fake ports. Live model-service smoke vẫn cần
endpoint và credential thật do môi trường triển khai cung cấp.
