# Iteration 301 — dọn alias policy asset khỏi root UI

## Phạm vi

Theo hướng Clean Code của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, root
`app.py` chỉ nên lắp ráp giao diện tương thích. Policy `approved_asset_paths`
đã thuộc `music_rag.ui_assets` và không được callback Gradio sử dụng; việc
export lại policy từ root là alias chết, làm mờ ranh giới ownership.

## Thay đổi

- Xóa import `approved_asset_paths` khỏi `app.py`.
- Cập nhật test app để chỉ kiểm tra khả năng dựng UI, không phụ thuộc alias
  private/legacy từ root.
- Mở rộng AST contract của Phase 7 để cấm alias `approved_asset_paths` quay lại
  root entrypoint.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_app.py tests/test_phase_7_legacy_ui_boundary.py`
  — **8 passed, 1 skipped** (Gradio chưa cài).
- Full offline suite: `uv run pytest` — **985 passed, 18 skipped, 1 warning**.
- `python -m compileall -q app.py src tests` — **đạt**.
- `git diff --check` — **đạt**; Git chỉ cảnh báo chuẩn hóa LF/CRLF trên Windows.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout không có endpoint, credential và production catalog thật.

## Kết luận

Slice này làm root UI mỏng hơn và giữ policy asset ở đúng module sở hữu, không
thay đổi hành vi render hoặc allow-list runtime.
