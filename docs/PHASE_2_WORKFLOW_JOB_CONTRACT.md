# Phase 2 — DTO workflow job

## Mục tiêu lát cắt

Triển khai phần nhỏ đầu tiên của Phase 2 trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: tạo typed domain DTO cho mapping
giữa workflow cục bộ và task xử lý từ xa. Lựa chọn là hướng Clean Code:
model bất biến, enum có tên ổn định và validation nằm ngay tại boundary.

## Thay đổi

- Tạo package `saxophone.workflows` với API công khai gồm `WorkflowJob`,
  `JobStatus` và `RemoteTaskType`.
- `WorkflowJob` giữ `job_id` cục bộ, `document_ref`, `task_type`,
  `idempotency_key`, trạng thái, số lần thử, thời điểm tạo và
  `remote_job_id` tùy chọn.
- Từ chối identifier rỗng hoặc chỉ có whitespace và `attempt <= 0` bằng
  `ValueError`; không tạo fallback dữ liệu sai.
- Enum task bao phủ các `task_type` đã nêu trong contract model service:
  `pdf_extract`, `figure_analyze`, `structure_label`, `embed`,
  `paragraph_tag`, `tag_resolve`, `retrieval_select`, `answer_generate`.

## Bằng chứng kiểm chứng

Lệnh chạy:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase_2_workflow_job_contract.py --basetemp=.pytest-tmp
```

Kết quả kiểm chứng hiện tại: **7 passed** cho contract test của lát cắt này.

Lát cắt này chỉ tạo contract/domain model; chưa có persistence repository,
remote submit/poll hay API job-status. Những phần đó vẫn thuộc các lát cắt
Phase 2 tiếp theo và không được giả nhận là đã hoàn tất.
