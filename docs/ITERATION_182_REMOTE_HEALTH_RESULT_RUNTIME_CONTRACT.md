# Iteration 182 - Runtime contract cua RemoteGpuHealth

## Pham vi

Kiem soat runtime cho DTO health cong khai. `Literal` chi ho tro type checker;
neu khong co guard tai constructor, gateway hoac fake gateway van co the tao
status la va capability khong an toan roi dua vao API health.

## Thay doi

- `RemoteGpuHealth` chi chap nhan ba status: `ready`, `degraded`, `unavailable`.
- Capability phai la tuple cac chuoi khong rong, khong co control character va
  khong trung lap.
- Bo sung regression tests cho status khong hop le, capability rong, capability
  co control character va capability trung lap.

## Bang chung kiem thu

- Test moi that bai truoc khi sua: constructor chap nhan status/capability sai.
- Sau khi sua: `uv run pytest -q tests/test_phase_1_remote_gpu_http.py` - **18 passed**.
- Full suite: `uv run pytest -q` - **749 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` va `git diff --check` deu dat.

## Gioi han bang chung

Day la kiem thu offline voi HTTP mock; live model-service smoke va production
golden parity van chua the xac minh vi checkout thieu endpoint, credential va
catalog production duoc phe duyet.
