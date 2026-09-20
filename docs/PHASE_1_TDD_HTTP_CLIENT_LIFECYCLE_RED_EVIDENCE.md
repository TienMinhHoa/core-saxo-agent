# Phase 1 - TDD RED: wiring va lifecycle HTTP client

## Pham vi lat cat

Lat cat nay khoa contract con thieu sau khi `HttpRemoteGpuGateway` da co adapter
health: composition root phai tao mot `httpx.AsyncClient` dung chung, dung no de
tao gateway mac dinh, va dong client cung ASGI lifespan. Chua them route moi,
khong goi GPU that, khong them submit/poll/cancel job.

## Contract duoc them truoc implementation

`test_default_composition_owns_one_http_client_and_closes_it_with_lifespan`
quy dinh ro:

- `create_app(settings)` mac dinh dung `HttpRemoteGpuGateway`, khong dung
  fallback unavailable khi cau hinh da hop le;
- `AppContainer` so huu mot `httpx.AsyncClient` dung chung de adapter khong tu
  tao client theo request;
- client con mo trong lifespan va da dong sau khi `TestClient` ket thuc.

Override fake gateway cua test cu van duoc giu nguyen de cac test route offline
khong can mang/GPU that.

## Bang chung RED da chay

Chay:

```powershell
uv run pytest tests/test_phase_1_composition_root.py -q
```

Ket qua thuc te: `1 failed, 5 passed, 1 warning in 1.91s`.

Assertion dau tien fail dung nhu du kien: default gateway la
`UnavailableRemoteGpuGateway`, khong phai `HttpRemoteGpuGateway`. Vi the test
chua den assertion `http_client`; contract nay hien dang khoa ca hai yeu cau
wiring va lifecycle. Warning la deprecation cua Starlette test client, khong
lien quan GPU/provider.

## Gioi han

Chua chay full suite o trang thai RED. Iteration GREEN ke tiep se chi wiring
lifecycle trong composition root, sau do chay lai test muc tieu, full suite,
`compileall`, va `git diff --check`.
