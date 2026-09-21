# Iteration 276 — ranh giới policy asset của UI legacy

## Mục tiêu

Giảm business logic còn nằm trong root `app.py` theo exit criteria Phase 7,
nhưng vẫn giữ nguyên API tương thích `approved_asset_paths` cho Gradio UI và
các caller hiện tại.

## Thay đổi

- Tách policy lọc asset đã duyệt, kiểm tra `access_scope` và kiểm tra path nằm
  trong `asset_root` sang `music_rag.ui_assets.approved_asset_paths`.
- Root `app.py` chỉ re-export hàm policy để không phá import cũ.
- Thêm regression assertion bảo đảm symbol legacy và policy module là cùng một
  callable, tránh tạo hai implementation trôi dạt.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_app.py -q`.
- Full offline suite: `uv run pytest -q`.
- Static: `uv run python -m compileall -q app.py src tests`.
- Hygiene: `git diff --check`.

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout không có endpoint, credential và catalog production thực tế.
