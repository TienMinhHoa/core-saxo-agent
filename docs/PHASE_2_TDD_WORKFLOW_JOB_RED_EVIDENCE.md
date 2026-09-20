# Phase 2 - TDD RED: contract WorkflowJob

## Pham vi lat cat

Lat cat nay khoa DTO typed nho nhat cho workflow job. DTO phai giu du thong tin
can persist de recovery/reconcile: local `job_id`, `remote_job_id` (khi da
submit), `document_ref`, `task_type`, `idempotency_key`, trang thai, so lan thu
va thoi diem tao. Khong chon JSON hay SQLite, khong them repository, executor,
route hay GPU workload.

## Contract duoc them truoc implementation

`tests/test_phase_2_workflow_job_contract.py` yeu cau:

- `RemoteTaskType` va `JobStatus` la enum typed, de application khong truyen
  chuoi tu do cho contract remote;
- `WorkflowJob` immutable luu nguyen mapping local-remote va metadata phuc vu
  idempotency/recovery;
- cac identifier duoc persist khong rong/chi co khoang trang; `remote_job_id`
  chi duoc phep `None` truoc khi submit;
- `attempt` phai la so nguyen duong.

Day la contract tu plan: remote job dung cac trang thai `queued`, `running`,
`succeeded`, `failed`, `cancelled`; local/remote id, stage, attempt va
idempotency key phai duoc persist truoc poll. Contract khong tu dat chinh sach
resume hay storage backend.

## Bang chung RED da chay

Chay:

```powershell
uv run pytest tests/test_phase_2_workflow_job_contract.py -q
```

Ket qua thuc te: `1 error in 0.49s` trong luc collect test, voi
`ModuleNotFoundError: No module named 'saxophone.workflows'`. Day la RED dung
nhu du kien: target package chua ton tai, chua co implementation nao co the
lam test xanh gia. Lanh vuc implementation ke tiep chi can tao typed model
khong phu thuoc FastAPI, HTTP client, Chroma hay GPU server, roi chay lai test
muc tieu va full suite.

## Gioi han

Chua co `JobRepository` hay recovery service, nen chua the khang dinh job state
duoc persist qua restart. Adapter JSON/SQLite va chinh sach resume van la lat
cat tiep theo, can contract test rieng.
