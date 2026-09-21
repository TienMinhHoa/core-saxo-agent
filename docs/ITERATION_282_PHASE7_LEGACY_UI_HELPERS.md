# Iteration 282 — tách policy UI thuần khỏi root entrypoint

## Phạm vi

Lát cắt này xử lý phần nhỏ còn lại của Phase 7: các helper policy thuần của
compatibility Gradio UI không nên là nơi sở hữu logic trong `app.py`. Không
thay đổi API công khai của entrypoint; các tên tương thích vẫn được giữ lại.

## Thay đổi

- Thêm `music_rag.ui_rendering` cho mapping status cố định và allow-list ảnh
  Chroma có kiểm tra path an toàn.
- `app.py` ủy quyền các policy này qua package namespace; code gọi cũ vẫn có
  thể dùng `chroma_asset_paths` và `_display_status`.
- Thêm contract test bảo vệ module helper và import boundary.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest -q tests/test_phase_7_legacy_ui_boundary.py tests/test_app.py --basetemp=.pytest-tmp` → **2 passed, 1 skipped**.
- Full offline: `uv run pytest -q --basetemp=.pytest-tmp` → **967 passed, 18 skipped, 1 warning**.
- Các test skip là do Gradio chưa cài, sample source thiếu hoặc quyền tạo
  symbolic link trên Windows; không phải test failure.
- Live model-service smoke và production golden parity vẫn chưa thể chạy vì
  checkout không có endpoint, credential và catalog production được phê duyệt.
