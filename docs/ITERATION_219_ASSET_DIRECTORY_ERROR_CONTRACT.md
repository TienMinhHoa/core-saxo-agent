# Iteration 219 — Chuẩn hóa lỗi đọc artifact là thư mục

## Phạm vi

Tiếp tục harden boundary `GET /api/v1/assets/{asset_ref:path}` theo kế hoạch
kiến trúc: lỗi filesystem không được thoát thành HTTP 500 ngoài ý muốn.

## Thay đổi

- Bổ sung mapping `IsADirectoryError` từ `ArtifactRepository` thành HTTP **404**
  với detail ổn định `asset not found`.
- Giữ nguyên nguyên tắc fail-closed: route không trả nội dung khi identity
  artifact trỏ vào thư mục, và không làm lộ đường dẫn nội bộ.
- Thêm API regression test mô phỏng repository trả `IsADirectoryError`.

## Bằng chứng kiểm thử

- Targeted API contract: `39 passed, 1 warning` với
  `uv run pytest tests/test_phase_7_api_routes.py -q`.
- Full offline suite: `907 passed, 3 skipped, 1 warning`.
- `python -m compileall -q src tests` thành công; `git diff --check` không phát
  hiện lỗi (chỉ có cảnh báo chuyển đổi LF/CRLF của Git trên Windows).

## Giới hạn xác minh

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và production catalog thật.
