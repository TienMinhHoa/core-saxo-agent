# Phase 1 - Timeout cho remote health

## Phạm vi

Health của model service/remote GPU là một HTTP dependency trong composition
root. Trước lát cắt này, `HttpRemoteGpuGateway` không truyền timeout riêng cho
request health, nên một upstream treo có thể giữ request `/api/v1/health` quá
lâu. Theo hướng Clean Code, timeout được đưa vào settings và truyền qua adapter,
không để route tự biết chi tiết HTTP client.

## Thay đổi

- Thêm `SAXO_REMOTE_GPU_HEALTH_TIMEOUT_SECONDS`, mặc định `5` giây và phải là
  số dương.
- `HttpRemoteGpuGateway` nhận timeout tường minh và truyền nó vào shared
  `httpx.AsyncClient` request.
- Composition root lấy timeout từ `AppSettings`; health failure vẫn trả trạng
  thái an toàn `unavailable` như trước.

## Bằng chứng

- Contract test xác nhận request health mang timeout cấu hình `2.5` giây.
- Settings tests xác nhận default, parsing giá trị `2.5` và reject `0`/số âm.
- `uv run pytest -q tests/test_phase_1_remote_gpu_http.py tests/test_phase_1_settings.py`:
  **31 passed**.
- Nhóm `tests/test_phase_1_remote_gpu_http.py` và
  `tests/test_phase_1_settings.py`: **25 passed**.
- Nhóm `tests/test_phase_1_composition_root.py`: **16 passed, 1 failed** do
  test import hiện hữu bị monkeypatch môi trường của `gettext`/`uvicorn`;
  failure xảy ra trước khi composition root được kiểm tra và không liên quan
  timeout.

## Giới hạn xác minh

Chưa có live model-service/Chroma endpoint trong checkout để thực hiện smoke
test production. Lát cắt này chỉ chứng minh timeout được wiring đúng ở boundary
offline.
