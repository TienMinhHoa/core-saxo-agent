# Phase 1 - Test plan TDD cho settings va composition root

## Muc dich va pham vi

Day la bo test cases de duyet truoc khi viet implementation cua lat cat
Phase 1 dau tien. Lat cat nay chi tao package `saxophone`, typed
`AppSettings`, composition root va endpoint health offline. No khong di chuyen
`pdf_layout_web.py`, khong goi Paddle/CUDA, khong ket noi Chroma, va khong goi
GPU server that.

Plan nay cu the hoa exit criteria cua
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` (Phase 1) va ADR-001. Cac ten bien moi
duoc chon theo prefix `SAXO_` de tranh tron voi `MUSIC_RAG_*` va `PDF_LAYOUT_*`
cua compatibility path cu.

## Contract cau hinh de test

`AppSettings.from_environment(environment)` la diem doc environment duy nhat.
Tham so `environment` la mapping de test khong can sua `os.environ` that.
Composition root nhan `AppSettings` da validate; route va use case khong doc
environment.

| Bien | Quy tac contract |
|---|---|
| `SAXO_DATA_ROOT` | Tuy chon; neu khong co, dung `runtime/saxophone`. Gia tri phai la duong dan tuong doi an toan hoac absolute path hop le. |
| `SAXO_REMOTE_GPU_BASE_URL` | Bat buoc; phai la HTTPS absolute URL, khong co query/fragment va khong co user-info. |
| `SAXO_REMOTE_GPU_BEARER_TOKEN` | Bat buoc; chuoi khong rong sau khi trim. Token khong duoc dua vao `repr`, response hay log. |
| `SAXO_REMOTE_GPU_TLS_VERIFY` | Tuy chon; mac dinh `true`; chi nhan `true` hoac `false` (khong phan biet hoa thuong). |
| `SAXO_REMOTE_GPU_MAX_IN_FLIGHT` | Tuy chon; mac dinh `4`; phai la so nguyen duong. |
| `SAXO_REMOTE_GPU_RETENTION_DAYS` | Tuy chon; mac dinh `30`; phai la so nguyen duong theo ADR-001. |

Khong dua timeout/retry/profile allowlist vao lat cat nay: chung la contract cua
`RemoteGpuGateway`, duoc them kem fake-server tests o lat cat tiep theo. Cach
tach nay giu doi thay doi nho va khong tao gateway nua voii config chua duoc
kiem chung.

## Test cases phai viet truoc implementation

### A. Unit test `AppSettings`

1. `from_environment` tao settings khi co base URL HTTPS va bearer token; cac
   default data root, TLS, in-flight va retention phai dung nhu bang tren.
2. Cac gia tri hop le explicit phai override default va giu dung kieu
   `Path`/`bool`/`int`.
3. Thieu base URL hoac token phai tra loi validation typed; message neu ten
   bien gay loi nhung khong lo token.
4. Base URL `http`, relative URL, URL co user-info, query hoac fragment phai
   bi tu choi.
5. Boolean va integer sai dinh dang, zero hay so am phai bi tu choi.
6. `repr(settings)` va exception validation khong chua bearer token.

### B. Unit/API test composition root

1. Import `saxophone.main` va `saxophone.app.factory` khong doc environment,
   khong mo HTTP client, khong import Paddle/CUDA/Gradio.
2. `create_app(settings, overrides=...)` tao dung mot `FastAPI` app va gan
   container vao `app.state`; adapter concrete chi duoc lap rap tai day.
3. `GET /api/v1/health` dung fake gateway tu `overrides`, khong goi network,
   va tra schema on dinh: `app`, `remote_gpu`, `extraction`, `ingestion`,
   `retrieval`, `chat`.
4. Fake gateway bao `ready`, `degraded`, hoac `unavailable` phai duoc map
   nguyen trang thai `remote_gpu`; cac capability chua migrate la `disabled`.
5. Health khong duoc phoi bay bearer token, URL ky, local filesystem path hay
   exception stack trace.

## Tieu chi pass va bang chung can ghi

- Test moi chay offline bang `uv run pytest --basetemp=.pytest-tmp`.
- Khong co test nao phu thuoc GPU, CUDA, Paddle, Chroma, OpenAI/DeepSeek hay
  browser.
- Truoc khi viet implementation, test A va B phai duoc trinh duyet va duoc
  chay o trang thai red vi package `saxophone` chua ton tai.
- Sau implementation toi thieu, cung lenh tren phai pass; ket qua va gioi han
  offline/live se duoc ghi vao tai lieu bang chung cua iteration do.

## Ly do chon Clean Code

Config la input khong tin cay tu moi truong, nen validate tai mot cua vao va
truyen object typed vao composition root. Fake gateway cho phep test health
nhu mot hop dong, khong bien unit test thanh mot cuoc goi GPU that - con quai
vat be ti hon nay khong can an CUDA trong bua sang.
