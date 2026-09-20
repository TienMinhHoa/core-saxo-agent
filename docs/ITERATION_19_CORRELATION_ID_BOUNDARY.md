# Iteration 19 — correlation ID ở ASGI boundary

## Phạm vi

Chuẩn hóa một correlation ID cho mọi HTTP request của backend. Client có thể
gửi `X-Correlation-ID` với ký tự an toàn; nếu thiếu hoặc không hợp lệ, backend
tạo UUID mới. Response luôn trả lại ID qua cùng header và lưu tại
`request.state.correlation_id` để các stage observability dùng tiếp.

Đây là lát cắt boundary-only: chưa tự ý thêm log payload, token usage hay thay
đổi workflow/model contract.

## Thay đổi

- Thêm HTTP middleware trong composition root.
- Chỉ chấp nhận ID dài tối đa 128 ký tự gồm chữ, số, `.`, `_`, `:`, `-`.
- Không ghi correlation ID vào body hoặc log secret; response header được áp
  dụng cả khi ID đầu vào thiếu/hỏng.
- Thêm test cho ID hợp lệ và trường hợp thiếu/không hợp lệ.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_7_api_routes.py -q` — đạt.
- `uv run pytest -q` — đạt.
- `uv run python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt.

Các kiểm tra trên chỉ chứng minh behavior offline của checkout. Live
model-service smoke vẫn chưa thể chạy vì chưa có endpoint, credential và
catalog production thật.
