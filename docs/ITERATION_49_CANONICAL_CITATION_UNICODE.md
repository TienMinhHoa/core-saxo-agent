# Bằng chứng Iteration 49 — citation ref Unicode canonical

## Phạm vi

Siết hợp đồng `ChatResult.citations` để citation đi qua chat boundary phải ở
dạng Unicode NFC canonical. Hai chuỗi nhìn giống nhau nhưng khác biểu diễn
Unicode không được coi là cùng một provenance ref một cách âm thầm.

## Thay đổi

- Bổ sung kiểm tra NFC trong `src/saxophone/chat/models.py`.
- Bổ sung regression test cho citation dùng dạng decomposed Unicode (`e` + dấu
  sắc tách rời).

## Kiểm chứng

- `uv run pytest -q tests/test_chat_answer_question.py`
- `uv run python -m compileall -q src tests`
- `git diff --check`

Các lệnh trên được chạy ở cuối iteration; kết quả được ghi lại trong báo cáo
GNHF. Live model-service smoke vẫn chưa thể chạy vì checkout không có endpoint,
credential và catalog production thật.

## Liên hệ yêu cầu kiến trúc

Invariant này bảo toàn source provenance khi citation được chuyển từ retrieval
sang chat, đồng thời tránh việc các biểu diễn Unicode tương đương tạo ra hai
identity khác nhau trong response.
