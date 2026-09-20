# Iteration 188 - hop dong runtime cho path va TLS boolean cua AppSettings

## Pham vi

Tiep tuc Phase 1 cua ke hoach refactor: `AppSettings` phai giu cung hop dong
khi duoc tao truc tiep, khong chi khi doc tu environment. Don vi nho cua
iteration nay la hai duong dan typed (`data_root`, `chroma_persist_directory`)
va co TLS (`remote_gpu_tls_verify`).

## Thay doi

- `AppSettings.__post_init__` tu choi gia tri khong phai `pathlib.Path` cho hai
  truong duong dan.
- `AppSettings.__post_init__` tu choi gia tri khong phai `bool` cho co TLS.
- Bo sung ba regression test de bao ve runtime boundary khi direct
  construction, tranh bypass cac parser cua `from_environment`.

## Bang chung kiem chung

- `uv run pytest -q tests/test_phase_1_settings.py`: **59 passed**.
- `uv run pytest -q`: **777 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: dat.
- `git diff --check`: dat.

## Trang thai con lai

Live model-service smoke va production golden parity van chua the xac minh vi
checkout chua co endpoint, credential va catalog production duoc cap phep.

