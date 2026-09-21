# Iteration 296 - Tách policy chọn record Chroma khỏi root UI

## Phạm vi

Tách một policy thuần khỏi `app.py`: lấy các `record` hợp lệ từ response của
Chroma trước khi render. Đây là bước nhỏ tiếp theo của Phase 7, giữ `app.py`
ở vai trò wiring/callback và gom việc kiểm tra shape dữ liệu vào
`music_rag.ui_workflows`.

## Thay đổi

- Thêm `select_chroma_records(response)` với contract an toàn:
  - response không phải mapping hoặc `items` không phải sequence thì trả `[]`;
  - bỏ qua item không phải mapping và record không phải dictionary;
  - giữ nguyên thứ tự và duplicate vì renderer cần phản ánh các hit nhận được.
- Callback `ask_chroma()` dùng policy mới thay cho list comprehension inline.
- Thêm contract test cho happy path, shape lỗi và duplicate.
- Thêm guard AST để root entrypoint phải dùng helper từ `ui_workflows`.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_7_ui_workflow_policy.py -q`: **6 passed**.
- `uv run pytest -q`: **981 passed, 18 skipped, 1 warning**.
- Các test bị skip đều do Gradio/sample source chưa có hoặc Windows account
  không được tạo symbolic link; không có test failure.
- `compileall` và `git diff --check` cũng được chạy ở bước xác minh cuối
  iteration và không phát hiện lỗi.

## Trạng thái còn lại

Live model-service smoke và production golden parity chưa thể xác minh trong
checkout này vì chưa có endpoint, credential và catalog production được cấp.
