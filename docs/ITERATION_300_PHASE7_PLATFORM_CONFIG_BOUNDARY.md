# Iteration 300 — ranh giới cấu hình cho adapter hạ tầng

## Phạm vi

Theo hướng Clean Code của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, adapter hạ tầng
không nên phụ thuộc ngược vào module composition root `saxophone.app.settings`.
Lát cắt này chỉ xử lý hai adapter đang vi phạm quy tắc đó:

- `saxophone.platform.chroma`;
- `saxophone.platform.remote_gpu`.

## Thay đổi

- Thay import runtime `AppSettings` bằng `Protocol` mô tả đúng các thuộc tính cấu
  hình mà adapter cần (`ChromaSettings`, `RemoteGpuSettings`).
- Giữ nguyên API runtime: composition root vẫn truyền `AppSettings`, vì object này
  thỏa structural contract; không đổi hành vi tạo Chroma hoặc health gateway.
- Thêm AST contract test để ngăn adapter hạ tầng tái phụ thuộc
  `saxophone.app.settings`.

## Bằng chứng kiểm chứng

- TDD targeted: trước refactor, contract test bắt đúng 2 vi phạm; sau refactor,
  `24 passed` cho dependency boundary, remote GPU HTTP contract và Chroma live
  contract (offline/mocked).
- Full suite: `985 passed, 18 skipped, 1 warning` trong `40.97s`.
- `uv run python -m compileall -q app.py src tests` thành công; `git diff --check`
  không phát hiện lỗi whitespace.
- Live model-service smoke và production golden parity chưa được chạy vì checkout
  không có endpoint, credential và catalog production được phê duyệt.

## Đánh giá

Adapter hạ tầng giờ phụ thuộc vào capability cấu hình tối thiểu thay vì biết module
composition root. Điều này làm rõ dependency direction và vẫn giữ tương thích với
`AppSettings` hiện tại.
