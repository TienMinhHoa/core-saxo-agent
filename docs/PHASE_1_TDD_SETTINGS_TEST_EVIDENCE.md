# Bang chung TDD Phase 1 - AppSettings

## Pham vi iteration 4

Da hoan thanh lat cat `AppSettings` cua Phase 1 theo TDD. Package
`saxophone.app.settings` da la cua vao cau hinh typed; chua tao composition
root, FastAPI route hay `RemoteGpuGateway`.

## Contract da duoc khoa bang test

- Chi `SAXO_REMOTE_GPU_BASE_URL` HTTPS hop le va
  `SAXO_REMOTE_GPU_BEARER_TOKEN` khong rong moi duoc chap nhan.
- Gia tri mac dinh gom `runtime/saxophone`, TLS verify `true`, toi da 4 job
  dang chay va retention 30 ngay.
- URL khong an toan (HTTP, relative, user-info, query, fragment), boolean sai,
  va so nguyen khong duong deu phai bi tu choi.
- `repr` va loi validation khong duoc lam lo bearer token.

## Thay doi da thuc hien

- Tao package `saxophone` va module `saxophone.app.settings`.
- `AppSettings.from_environment(environment)` nhan mapping explicit, validate
  base URL HTTPS, bearer token, boolean va so nguyen duong, sau do tra object
  immutable typed.
- Token dung `repr=False`; thong bao validation chi neu ten bien, khong noi
  gia tri bi mat.
- Them `saxophone*` vao setuptools package discovery de `uv` build va import
  package moi nhu mot phan cua backend.

## Bang chung kiem thu offline

Lenh da chay (Windows/PowerShell):

```powershell
uv run pytest tests/test_phase_1_settings.py --basetemp=.pytest-tmp
```

Ket qua iteration 3 truoc implementation: test collection that bai voi
`ModuleNotFoundError: No module named 'saxophone'`. Day la trang thai TDD RED
co chu dich.

Ket qua iteration 4 sau implementation: `16 passed in 0.16s`.

Dong thoi da chay regression cua code cu, loai tru file RED moi:

```powershell
uv run pytest --ignore=tests/test_phase_1_settings.py --basetemp=.pytest-tmp
```

Ket qua iteration 4: `42 passed, 2 skipped in 1.21s`. Hai skip da biet la
Gradio chua cai va sample source khong co trong checkout.

Kiem tra cu phap package va whitespace Git cung da pass:

```powershell
uv run python -m compileall -q src\saxophone
git diff --check
```

Day la kiem thu offline; khong co GPU server that nao duoc goi.

## Gioi han va buoc tiep theo

Buoc tiep theo cua Phase 1 la viet test RED cho composition root va health
endpoint dung fake gateway. Khong duoc khoi tao HTTP client hay doc environment
khi import module; day la hang rao de backend khong vo tinh goi GPU that.
