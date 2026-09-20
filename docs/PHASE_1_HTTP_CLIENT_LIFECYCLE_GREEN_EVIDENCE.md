# Phase 1 - GREEN: wiring HTTP gateway va ASGI lifespan

## Pham vi lat cat

Hoan tat contract RED cua lifecycle HTTP client: `create_app(settings)` tao mot
`httpx.AsyncClient` dung chung, dung client do cho `HttpRemoteGpuGateway` mac
dinh va dong no khi ASGI lifespan ket thuc. Khong them route, khong goi GPU
that, khong them submit/poll/cancel job.

## Ket qua thuc hien

- `AppContainer` cong khai client do mot ung dung so huu; gateway HTTP mac dinh
  nhan dung cung instance nay, khong tu tao client theo request.
- `FastAPI(lifespan=...)` dong client trong `finally`, nen ca truong hop
  shutdown binh thuong cua ASGI van giai phong ket noi.
- `AppOverrides(remote_gpu_gateway=...)` van duoc giu cho fake gateway trong
  test route offline; default production khong con roi ve gateway unavailable
  khi settings hop le.

## Bang chung kiem chung offline

Chay sau khi trien khai:

```powershell
uv run pytest tests/test_phase_1_composition_root.py -q
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

Ket qua thuc te:

```text
tests/test_phase_1_composition_root.py: 6 passed, 1 warning
full suite: 52 passed, 2 skipped, 1 warning
```

`compileall` va `git diff --check` hoan tat khong bao loi. Hai skip da biet:
Gradio la dependency optional chua cai va sample source khong co trong checkout.
Warning la deprecation tu Starlette test client, khong lien quan den gateway hay
lifecycle.

Khong co GPU, CUDA hay dich vu mang that nao duoc goi: test lifecycle chi dung
`TestClient` cua ASGI va kiem tra trang thai `is_closed` cua client.

## Ranh gioi con lai

Lat cat nay chi hoan tat wiring/lifecycle cho health gateway. Phase 1 van can
migrate cac API extraction, job, search, chat va layout vao cung FastAPI app;
remote submit/poll/cancel, retry va recovery cung chua duoc trien khai.
