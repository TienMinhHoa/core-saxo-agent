# Bằng chứng TDD Phase 1 - composition root và health

## Phạm vi iteration 5

Đã bổ sung contract test **RED** cho lát cắt còn thiếu của Phase 1: composition
root duy nhất và `GET /api/v1/health`. Chưa viết `saxophone.main`, factory,
container hay HTTP gateway thật trong iteration này; giữ đúng thứ tự TDD để
contract đi trước runtime.

## Contract vừa được khóa

- Import `saxophone.main` và `saxophone.app.factory` không được đọc environment
  tiến trình, không khởi tạo provider hay gọi mạng.
- `create_app(settings, overrides)` phải lắp một đối tượng `FastAPI`, lưu một
  `AppContainer` vào `app.state`, và chỉ nhận gateway fake qua `overrides`.
- `GET /api/v1/health` phải gọi port async của fake gateway đúng một lần, trả
  schema ổn định gồm `app`, `remote_gpu`, `extraction`, `ingestion`,
  `retrieval`, `chat`.
- Trạng thái `ready`, `degraded`, `unavailable` của GPU phải được giữ nguyên;
  bốn capability chưa migrate là `disabled`.
- Health response không được lộ bearer token, URL GPU hoặc đường dẫn dữ liệu
  cục bộ.

## Bằng chứng RED offline

Lệnh đã chạy:

```powershell
uv run pytest tests/test_phase_1_composition_root.py --basetemp=.pytest-tmp
```

Kết quả mong đợi trước implementation: collection dừng với
`ModuleNotFoundError: No module named 'saxophone.app.factory'`. Đây là RED có
chủ đích: package settings đã tồn tại, còn factory/main/platform chưa tồn tại.
Không có GPU, CUDA, Paddle, Chroma hoặc dịch vụ mạng thật nào được gọi.

Regression độc lập cho lát cắt đã hoàn thành vẫn xanh:

```powershell
uv run pytest tests/test_phase_1_settings.py --basetemp=.pytest-tmp
```

Kết quả: `16 passed in 0.11s`. Đồng thời `uv run python -m compileall -q tests`
và `git diff --check` đều không báo lỗi. Không chạy full suite trong iteration
RED này vì test contract mới được chủ động giữ đỏ cho đến lát cắt implementation
kế tiếp.

## Bước kế tiếp

Triển khai tối thiểu các module `saxophone.main`, `saxophone.app.factory` và
port/model `saxophone.platform.remote_gpu` để làm xanh đúng contract trên.
Gateway HTTP lifecycle-safe và fake HTTP server đầy đủ vẫn là lát cắt sau;
iteration kế tiếp không được thay đổi extraction, retrieval, chat hay UI cũ.
