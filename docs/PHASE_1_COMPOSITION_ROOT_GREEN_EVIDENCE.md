# Bằng chứng Phase 1 — composition root và health (GREEN)

## Phạm vi iteration 6

Hoàn thành lát cắt tối thiểu đã được khóa bởi test TDD của iteration 5:
package `saxophone` hiện có một composition root FastAPI, container dependency
tường minh, cùng port GPU bất đồng bộ. Đây chưa phải migration extraction,
ingestion, retrieval, chat hoặc UI; các capability đó được trả về là
`disabled` để API không hứa điều chưa được nối dây.

## Kết quả thực hiện

- `saxophone.app.factory.create_app(settings, overrides)` tạo duy nhất một
  đối tượng ASGI `FastAPI`, gắn `AppContainer` vào `app.state.container` và
  chỉ nhận dependency fake qua `AppOverrides`.
- `saxophone.platform.remote_gpu` định nghĩa `RemoteGpuGateway` task-neutral,
  DTO `RemoteGpuHealth` và fallback `UnavailableRemoteGpuGateway`. Fallback
  không tạo HTTP client, không gọi mạng và không chạy GPU; adapter HTTP
  submit/poll thật vẫn là lát cắt kế tiếp phía sau port này.
- `GET /api/v1/health` await gateway đúng một lần và chỉ công bố schema an
  toàn: trạng thái app/GPU cùng bốn capability chưa migrate là `disabled`.
  Response không đưa bearer token, URL GPU hay đường dẫn dữ liệu ra ngoài.
- `saxophone.main` không đọc environment khi import. Hàm
  `create_application()` là ranh giới tiến trình duy nhất có thể nhận
  environment để build settings rồi gọi factory.

## Bằng chứng kiểm chứng offline

Đã chạy tại repository checkout hiện tại:

```powershell
uv run pytest tests/test_phase_1_composition_root.py tests/test_phase_1_settings.py --basetemp=.pytest-tmp -q
# 21 passed, 1 warning

uv run pytest --basetemp=.pytest-tmp -q
# 47 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

Hai test skip không phải regression: một test yêu cầu optional dependency
Gradio chưa cài và một test yêu cầu sample source không nằm trong checkout.
Không có GPU, CUDA, Chroma, OCR hay mạng thật nào được gọi trong lần kiểm
chứng này.

## Giới hạn và bước tiếp theo

Phase 1 chưa đạt toàn bộ exit criteria: còn thiếu HTTP `RemoteGpuGateway`
với timeout/retry/lifecycle an toàn, health/capability cache, và migration
các API extraction/job/search/chat/layout vào cùng application. Lát cắt sau
nên viết contract test RED cho HTTP gateway trước, bao gồm auth không lộ bí
mật, timeout và mapping `ready|degraded|unavailable`.
