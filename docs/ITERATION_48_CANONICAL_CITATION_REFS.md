# Bằng chứng Iteration 48 — citation ref canonical

## Phạm vi

Siết hợp đồng `ChatResult.citations` để citation đi qua chat boundary phải là
source reference không rỗng và không có khoảng trắng ở đầu/cuối. Điều này giữ
cho chuỗi citation khớp chính xác với provenance do retrieval cung cấp và tránh
hai biểu diễn khác nhau của cùng một source ref.

## Thay đổi

- Bổ sung guard `citations must contain canonical refs` trong
  `src/saxophone/chat/models.py`.
- Bổ sung regression test cho citation có khoảng trắng đầu hoặc cuối trong
  `tests/test_chat_answer_question.py`.

## Kiểm chứng

- `uv run pytest -q tests/test_chat_answer_question.py` → **12 passed**.
- Chưa kết luận live model-service smoke; checkout vẫn không có endpoint,
  credential và catalog production để chạy kiểm chứng provider thật.

## Liên hệ yêu cầu kiến trúc

Guard này củng cố grounding rule: citation phải trỏ tới source ref/page/heading/
paragraph có thật và giữ provenance chính xác khi đi từ retrieval sang chat.
