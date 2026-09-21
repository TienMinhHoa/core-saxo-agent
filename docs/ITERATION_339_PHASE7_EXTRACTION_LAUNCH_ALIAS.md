# Iteration 339 — sửa xung đột tên bộ khởi chạy extraction PDF

## Phạm vi

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: kiểm tra boundary
giữa HTTP interface và workflow khởi chạy extraction PDF.

## Thay đổi

- Đổi alias import workflow từ `start_extraction` thành `launch_extraction` trong
  HTTP interface.
- Giữ tên route `start_extraction` để không đổi URL/API hiện có.
- Route nay gọi đúng workflow launcher thay vì tự gọi đệ quy vào chính route.
- Thêm regression test chứng minh route queue job, gọi launcher đúng một lần với
  các dependency đã compose, rồi trả public state.

## Bằng chứng

- Targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py -q` → **37 passed**.
- Full offline: `uv run pytest -q` → **1060 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt; chỉ còn cảnh báo chuyển đổi LF/CRLF của Git trên
  Windows, không có whitespace error.

## Giới hạn xác minh

Live model-service smoke và production parity vẫn chưa xác minh vì checkout này
chưa có endpoint, credential và production catalog được phê duyệt.
