# Iteration 287 - Dọn import UI chết trong root entrypoint

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: giữ `app.py` ở vai trò entrypoint/UI tương thích và loại bỏ các dependency/alias không còn được sử dụng sau khi policy UI đã chuyển sang facade `music_rag.ui_rendering`.

## Thay đổi

- Xóa import không sử dụng `MusicMaterialService` khỏi `app.py`.
- Xóa hai alias UI không được gọi (`_display_status`, `_render_source_bundle`); `app.py` chỉ giữ các facade UI thực sự dùng là `chroma_asset_paths` và `render_chroma_results`.
- Thêm contract test AST để ngăn các alias/import legacy này quay trở lại.

## Bằng chứng kiểm thử

- Red test trước implementation: `3 passed, 1 failed` đúng tại guard import chết.
- Targeted sau implementation: `uv run pytest -q tests/test_phase_7_legacy_ui_boundary.py` — `4 passed`.
- Full offline suite: `970 passed, 18 skipped, 1 warning` với `uv run pytest -q`.
- Syntax: `uv run python -m compileall -q app.py src tests` — đạt.
- Diff hygiene: `git diff --check` — đạt.

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì checkout không có endpoint, credential và catalog production được phê duyệt.
