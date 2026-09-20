# Iteration 198 - safe-path contract cho ten thiet bi Windows

## Pham vi

Tiep tuc hardening `AppSettings` theo yeu cau file-safety cua solution plan. Hai
path runtime (`data_root` va `chroma_persist_directory`) khong duoc chua thanh
phan ma Windows hieu la device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`,
`LPT1`-`LPT9`), ke ca khi co extension.

## Thay doi

- Bo sung `_validate_windows_device_path_components()` vao runtime path
  validation; ap dung dong nhat cho direct construction va environment parser.
- Bo sung 20 regression tests TDD cho hai field, device name viet hoa/thuong va
  ten co extension.
- Khong thay doi path hop le, traversal rule, control-character rule hoac
  contract cua model service.

## Bang chung

- Red test truoc implementation: **20 failed**, dung vi path device name chua
  bi tu choi.
- Targeted sau implementation:
  `uv run pytest tests/test_phase_1_settings.py -k
  'windows_device_path_components'` -> **20 passed**.
- Full suite: `uv run pytest -q` -> **830 passed, 3 skipped, 1 warning**;
  `compileall` va `git diff --check` deu thanh cong.
- Live model-service smoke va production golden parity van chua the xac minh vi
  checkout thieu endpoint, credential va catalog production that.
