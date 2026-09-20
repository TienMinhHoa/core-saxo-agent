# Iteration 45 - chặn citations khi thiếu bằng chứng

## Phạm vi

Tiếp tục siết DTO `ChatResult` tại ranh giới retrieval - chat theo kiến trúc
Clean Code. Khi trạng thái là `INSUFFICIENT_EVIDENCE`, kết quả không có answer,
evidence bundle hoặc citations; nếu không, API có thể phát ra nguồn trích dẫn dù
không có bằng chứng đã được chọn để grounding.

## Thay đổi

- Bổ sung invariant trong `ChatResult.__post_init__`: trạng thái thiếu bằng chứng
  phải có `citations == ()`.
- Bổ sung regression test chứng minh citations không được xuất hiện trong trạng
  thái thiếu bằng chứng.
- Không thay đổi happy path: `AnswerQuestion` vẫn trả citations duy nhất cho
  kết quả `ANSWERED`, còn nhánh không có hit vẫn trả tuple rỗng.

## Bằng chứng kiểm thử

- Trước implementation (TDD red): test mới **fail** vì DTO chưa từ chối
  citations trong trạng thái thiếu bằng chứng.
- Targeted: `uv run pytest tests/test_chat_answer_question.py -q` - **9 passed**.
- Full suite: sẽ được ghi nhận lại trong `REFACTOR_ACCEPTANCE_STATUS.md` sau khi
  chạy kiểm chứng iteration này.
- Kiểm tra bổ sung: `uv run python -m compileall -q src tests`, `git diff --check`.

Các kiểm tra trên là offline; live model-service smoke và production golden
parity vẫn cần endpoint, credential và catalog production thật.
