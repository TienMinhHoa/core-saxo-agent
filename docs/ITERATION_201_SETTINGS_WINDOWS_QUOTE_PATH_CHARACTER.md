# Iteration 201 - Bao phu ky tu nhay kep trong safe-path Windows

## Pham vi

Tiep tuc hoan tat coverage cho contract safe-path cua `AppSettings` sau
Iteration 200. Ky tu nhay kep (`"`) la mot trong cac ky tu Windows khong cho
phep trong ten file/thu muc, nhung bo test truoc do chua co case rieng cho ky
tu nay.

## Thay doi

- Bo sung regression test cho component path chua `"` tren ca hai field
  `data_root` va `chroma_persist_directory`.
- Kiem tra ca hai duong vao: direct construction va `from_environment`.
- Khong thay doi implementation vi `_validate_windows_device_path_components`
  da enforce dung contract `< > : " | ? *`; iteration nay khoa coverage con
  thieu bang test ro rang.

## Bang chung

- Targeted settings suite: `uv run pytest tests/test_phase_1_settings.py -q`
  -> **156 passed**.
- Full regression suite: `uv run pytest -q` -> **874 passed, 3 skipped, 1
  warning**.
- Syntax: `python -m compileall -q src tests` -> dat.
- Hygiene: `git diff --check` -> dat (chi canh bao LF/CRLF thong thuong cua
  Git tren Windows).

## Gioi han xac minh

Day la xac minh offline. Live model-service smoke va production golden parity
van chua the chay vi checkout chua co endpoint, credential va production
catalog duoc phe duyet.
