# Iteration 200 - Safe-path ky tu khong hop le tren Windows

## Pham vi

Tiep tuc harden hop dong safe-path cua `AppSettings` cho hai truong runtime
`data_root` va `chroma_persist_directory`. Muc tieu la tu choi cac path
component co ky tu ma Windows khong cho phep trong ten file, dac biet dau `:`
co the tao alternate data stream.

## Thay doi

- Bo sung validation fail-closed cho cac ky tu `< > : " | ? *` trong moi path
  component, nhung van bo qua drive anchor hop le.
- Bao ve ca direct construction va `from_environment`, giu hai duong vao dung
  mot contract.
- Viet test TDD cho 6 ky tu/shape tren ca hai field va ca hai cach khoi tao.

## Bang chung

- Truoc implementation: 24 test moi that bai vi contract chua duoc enforce.
- Sau implementation: `uv run pytest tests/test_phase_1_settings.py -q` ->
  **152 passed**.
- Regression suite: `uv run pytest -q` -> **870 passed, 3 skipped, 1 warning**.
- `python -m compileall -q src tests` -> dat.
- `git diff --check` -> dat; chi con warning LF/CRLF thong thuong cua Git tren
  Windows.

## Gioi han xac minh

Day la xac minh offline. Live model-service smoke va production golden parity
van chua the chay vi checkout chua co endpoint, credential va production
catalog duoc phe duyet.
