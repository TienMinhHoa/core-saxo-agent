# Iteration 194 - Chan path rong tai boundary AppSettings

## Pham vi

`AppSettings.from_environment(...)` da tu choi chuoi path rong, nhung tao
`AppSettings(...)` truc tiep voi `Path()` van duoc chap nhan. Trong pathlib,
`Path()` tuong duong voi `Path(".")`, nen adapter co the vo tinh ghi du lieu
vao thu muc hien tai thay vi thu muc runtime duoc cau hinh.

## Thay doi

- Bo sung guard trong `_validate_runtime_path(...)` de tu choi `Path(".")`,
  bao gom `Path()` va path duoc rut gon tu chuoi `.`.
- Ap dung cung mot guard cho `data_root` va `chroma_persist_directory` tai
  direct-construction boundary; loi van la `SettingsValidationError`.
- Them 2 regression tests TDD cho hai field.

## Bang chung

- Truoc implementation: 2 test moi that bai vi `Path()` khong bi tu choi.
- Sau implementation: targeted path tests **12 passed**.
- Targeted settings suite: **81 passed**.
- Full suite: **791 passed, 3 skipped, 8 errors**; 8 loi xay ra o setup khi
  pytest don SQLite Chroma dang bi khoa (`WinError 32`) tren Windows, khong
  nam trong settings tests va khong lien quan den patch nay.
- `python -m compileall -q src`: dat.
- `git diff --check`: dat; Git chi canh bao chuyen doi LF/CRLF tren Windows.

## Quy tac tong quat

Moi filesystem path di vao settings phai co gia tri thuc, khong chi co kieu
`Path`; can kiem tra ca path rong/hien tai, parent traversal va control
character truoc khi truyen cho adapter.
