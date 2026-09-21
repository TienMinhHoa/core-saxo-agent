# Iteration 295 — tách policy chọn evidence khỏi callback UI

## Phạm vi

Theo hướng Clean Code của kế hoạch refactor, iteration này chỉ xử lý một đơn vị
nhỏ trong Phase 7: policy chọn các `record` đưa vào Answer RAG không còn nằm
trực tiếp trong callback `ask_answer()` của root entrypoint `app.py`.

## Thay đổi

- Thêm `music_rag.ui_workflows.select_answer_records()` như một policy thuần:
  ưu tiên record do agent chọn, loại trùng theo `chunk_id`, sau đó bổ sung tối đa
  ba final hit còn lại.
- Giữ nguyên các guard hiện hữu: chỉ nhận mapping/record hợp lệ và chỉ nhận
  `chunk_id` dạng chuỗi; input sai trả về danh sách rỗng thay vì làm callback lỗi.
- `app.py` chỉ gọi policy public này; phần callback vẫn giữ nguyên UI và thông
  báo tương thích.
- Thêm contract tests cho thứ tự ưu tiên, deduplication, giới hạn final hits và
  input sai kiểu.

## Bằng chứng kiểm chứng

- TDD red trước implementation: module mới chưa tồn tại nên 3 test policy thất
  bại với `ModuleNotFoundError`.
- Targeted verification: `uv run pytest tests/test_phase_7_ui_workflow_policy.py tests/test_phase_7_legacy_ui_boundary.py`
  — **9 passed**.
- Full offline suite: `uv run pytest` — **977 passed, 18 skipped, 1 warning**.
- Static checks: `uv run python -m compileall -q app.py src tests` và
  `git diff --check` — đạt.
- Các test bị skip vẫn là các giới hạn môi trường đã biết (Gradio chưa cài,
  symbolic link Windows không có quyền, sample source không có); không có live
  model-service smoke trong checkout này vì thiếu endpoint/credential/catalog
  production.

## Kết luận

Slice policy UI workflow đã được tách và khóa bằng contract test, không thay đổi
public API của legacy Gradio UI. Stop condition tổng thể chưa đạt vì live smoke,
production golden parity và một số kiểm chứng runtime ngoài checkout vẫn chưa có
đầu vào để xác minh.
