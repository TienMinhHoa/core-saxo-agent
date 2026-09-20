# Iteration 43 - validation token usage qua ranh giới chat

## Mục tiêu

Đảm bảo `ChatResult`, cũng như `GeneratedAnswer`, không đưa token usage sai kiểu
hoặc giá trị âm qua ranh giới application/API. Đây là phần thực thi yêu cầu
typed result validation trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.

## Thay đổi

- Tách validation `token_usage` thành một quy tắc dùng chung trong
  `saxophone.chat.models`.
- Áp dụng quy tắc cho `ChatResult`; mapping phải có key không rỗng và value là
  số nguyên không âm, đồng thời loại `bool` dù Python coi `bool` là `int`.
- Bổ sung regression test cho giá trị âm, boolean và key chỉ chứa khoảng trắng.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_chat_answer_question.py` - đạt.
- Full suite: `uv run pytest` - đạt.
- Static: `uv run python -m compileall -q src tests` - đạt.
- Hygiene: `git diff --check` - đạt.

Các kiểm tra trên là offline; live model-service smoke vẫn cần endpoint và
credential thật nên không được suy diễn từ test fake thành bằng chứng production.
