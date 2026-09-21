# Iteration 297 - Phase 7: facade orchestration UI

## Phạm vi

Tách orchestration của hai callback Gradio `ask_chroma` và `ask_answer` khỏi
root entrypoint `app.py`. Root chỉ còn wiring service, scope và renderer vào
workflow facade; các policy chọn record vẫn dùng chung trong
`music_rag.ui_workflows`.

## Thay đổi

- Thêm `handle_chroma_request()` cho luồng hiểu câu hỏi, retrieval, xử lý lỗi,
  chọn record và render kết quả Chroma.
- Thêm `handle_answer_request()` cho luồng retrieval, chọn evidence, gọi answer
  agent, xử lý lỗi và format chi phí.
- Callback trong `app.py` chuyển sang gọi facade; giữ các tên `select_*` trong
  import compatibility để không phá contract AST hiện hữu.
- Thêm contract test bảo đảm input chỉ gồm whitespace bị chặn trước khi chạm
  service.

## Bằng chứng kiểm chứng

- Targeted UI/boundary tests: `15 passed`.
- Full offline suite: `983 passed, 18 skipped, 1 warning`.
- `python -m compileall -q app.py src tests`: đạt.
- `git diff --check`: đạt; chỉ có cảnh báo chuyển LF/CRLF của Git.
- Chưa chạy live model-service smoke hoặc production golden parity vì checkout
  vẫn không có endpoint, credential và production catalog.

## Việc còn lại

Đoạn implementation cũ sau lệnh `return` sớm trong `app.py` vẫn còn là dead
code tương thích lịch sử. Iteration tiếp theo nên xóa phần này bằng patch nhỏ,
sau đó siết AST contract để root entrypoint không còn business logic.
