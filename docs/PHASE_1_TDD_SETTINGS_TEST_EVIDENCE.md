# Bang chung TDD Phase 1 - AppSettings

## Pham vi iteration 3

Da chuyen phan `A. Unit test AppSettings` trong
`PHASE_1_TDD_TEST_PLAN.md` thanh test pytest co the thi hanh tai
`tests/test_phase_1_settings.py`. Day la lat cat nho nhat cua Phase 1:
chi khoa contract cau hinh, chua viet package `saxophone`, composition root,
FastAPI route hay RemoteGpuGateway.

## Contract da duoc khoa bang test

- Chi `SAXO_REMOTE_GPU_BASE_URL` HTTPS hop le va
  `SAXO_REMOTE_GPU_BEARER_TOKEN` khong rong moi duoc chap nhan.
- Gia tri mac dinh gom `runtime/saxophone`, TLS verify `true`, toi da 4 job
  dang chay va retention 30 ngay.
- URL khong an toan (HTTP, relative, user-info, query, fragment), boolean sai,
  va so nguyen khong duong deu phai bi tu choi.
- `repr` va loi validation khong duoc lam lo bearer token.

## Bang chung kiem thu offline

Lenh da chay (Windows/PowerShell):

```powershell
uv run pytest tests/test_phase_1_settings.py --basetemp=.pytest-tmp
```

Ket qua thuc te: test collection that bai voi
`ModuleNotFoundError: No module named 'saxophone'`, vi package dich chua duoc
tao. Day la trang thai TDD RED co chu dich, chung minh test dang bao ve
contract truoc implementation, khong phai regression cua chuc nang hien co.

Dong thoi da chay regression cua code cu, loai tru file RED moi:

```powershell
uv run pytest --ignore=tests/test_phase_1_settings.py --basetemp=.pytest-tmp
```

Ket qua: `26 passed, 2 skipped` trong 2.05 giay. Hai skip da biet la Gradio
chua cai va sample source khong co trong checkout.

## Gioi han va buoc tiep theo

Can duyet bo test nay truoc khi viet `saxophone.app.settings.AppSettings` va
`SettingsValidationError`. Sau khi implementation toi thieu, chay lai lenh
tren, sau do chay toan bo `uv run pytest --basetemp=.pytest-tmp` de bao dam
compatibility path cu khong bi anh huong.
