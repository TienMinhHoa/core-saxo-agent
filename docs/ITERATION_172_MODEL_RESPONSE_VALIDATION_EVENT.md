# Iteration 172 — failure event khi response model sai contract

## Mục tiêu

Đáp ứng yêu cầu observability của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
mọi request model thất bại phải có structured failure event an toàn, kể cả khi
HTTP transport thành công nhưng response không đúng typed contract.

## Thay đổi

- `LiteLLMModelClient` phát `model.request.failed` khi JSON response không hợp
  lệ, payload không phải mapping, task/model/schema bị drift hoặc output/source
  version không đúng contract.
- Event chỉ ghi metadata vận hành (`attempt`, `reason_code`, `output_count=0`),
  không ghi response payload hay source content.
- Bổ sung regression test cho response có `task_type` sai và xác minh event được
  phát trước khi `ModelValidationError` được ném lại cho caller.

## Kiểm chứng

- Targeted test: `tests/test_phase_1_litellm_client.py`.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi.
- Live model-service smoke vẫn chưa thực hiện vì checkout chưa có endpoint,
  credential và catalog production thật.
