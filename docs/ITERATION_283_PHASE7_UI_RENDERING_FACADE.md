# Iteration 283 - gom rendering UI vào facade package

## Phạm vi

Lát cắt này tiếp tục Phase 7 Cleanup và enforcement. Mục tiêu là đưa các helper
rendering thuần của compatibility Gradio UI ra khỏi trách nhiệm sở hữu của root
entrypoint, nhưng vẫn giữ các tên tương thích mà `app.py` đang gọi.

## Thay đổi

- Mở rộng `music_rag.ui_rendering` với `render_source_bundle` và
  `render_chroma_results`.
- Các helper mới giữ nguyên nguyên tắc an toàn hiện có: escape nội dung HTML,
  chỉ trả về sidecar image path hợp lệ và loại ảnh trùng.
- `app.py` nhận các helper qua package facade; không đổi contract gọi hiện tại.
- Contract test xác nhận facade public export đủ bốn helper UI và ngăn việc thêm
  lại helper rendering mới mà không qua boundary.

## Bằng chứng kiểm chứng

- Targeted boundary: `uv run pytest tests/test_phase_7_dependency_enforcement.py tests/test_phase_7_legacy_ui_boundary.py -q` - **41 passed**.
- Full offline: `uv run pytest -q` - **967 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q app.py src tests` - đạt.
- Các skip là do Gradio chưa cài, sample source thiếu hoặc Windows account không
  có quyền tạo symbolic link; không có test failure.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout không có endpoint, credential và production catalog được phê duyệt.

## Trạng thái

Lát cắt UI rendering đã có facade và regression guard; stop condition toàn bộ
chưa đóng do live smoke/parity vẫn là blocker môi trường ngoài checkout.
