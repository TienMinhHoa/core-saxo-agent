# Iteration 159 - Canonical text cho `ModelRequest`

## Phạm vi

Tiếp tục siết contract tại mục 12.5 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Request gửi model service phải fail-closed khi profile, schema hoặc idempotency key
không ở dạng text canonical; không được `.strip()` âm thầm thay đổi request.

## Thay đổi

- `ModelRequest.model` và `response_schema` dùng cùng quy tắc canonical với
  `ModelResponse`: non-blank, không whitespace đầu/cuối, không control character
  hoặc DEL, và đã chuẩn hóa Unicode NFC.
- `idempotency_key` tùy chọn cũng phải canonical khi có mặt.
- Bổ sung 9 regression cases cho whitespace, control character và Unicode chưa NFC.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_1_model_client_contract.py -q`: **34 passed**.
- Đã chạy TDD trước implementation: test mới ban đầu fail 9 trường hợp vì request
  còn tự động trim; sau khi sửa boundary, toàn bộ contract pass.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì checkout
  chưa có endpoint, credential và catalog production thật.

## Kết luận

Model request boundary hiện nhất quán với response boundary và không còn che khuất
contract drift bằng việc tự động chuẩn hóa text.
