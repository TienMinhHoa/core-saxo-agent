# Iteration 199 - safe-path cho thanh phan bi Windows cat bo

## Pham vi

Tiep tuc hardening `AppSettings` theo safe-path contract trong solution plan.
Windows tu dong cat dau cham hoac khoang trang o cuoi moi thanh phan path; vi
vay `runtime.` va `runtime ` co the bi alias thanh cung mot thu muc khac voi
gia tri ma operator nhin thay.

## Thay doi

- `AppSettings` tu choi moi path component ket thuc bang `.` hoac khoang trang.
- Sua `_parse_data_root()` va `_parse_chroma_directory()` giu nguyen raw path
  de runtime validator ap dung cung mot contract cho environment va direct
  construction; khong am tham strip ky tu co y nghia.
- Them 16 regression tests TDD cho ca hai field, ca hai cach khoi tao va ca
  path mot/tap component.

## Bang chung

- Red test truoc implementation: **12 failed, 4 passed**; cac case co dau cham
  da bi bo sot va cac case co khoang trang bi parser strip mat.
- Targeted sau implementation:
  `uv run pytest -q tests/test_phase_1_settings.py -k
  'trimmed_path_components or path'` -> **48 passed**.
- `python -m compileall -q src tests` -> thanh cong.
- Live model-service smoke va production golden parity van chua the xac minh vi
  checkout thieu endpoint, credential va catalog production that.
