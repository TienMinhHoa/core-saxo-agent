# Iteration 168 — endpoint sau chuẩn hoá không được rỗng

## Phạm vi

Tiếp tục harden contract của `LiteLLMModelClient` theo kiến trúc direct
LiteLLM request/response. Slice này chỉ xử lý một lỗi biên: endpoint chứa toàn
dấu `/` có thể vượt qua kiểm tra ban đầu nhưng trở thành chuỗi rỗng sau khi
chuẩn hoá.

## Thay đổi

- Thêm kiểm tra fail-closed sau `strip()` và `rstrip("/")`.
- Thêm 3 regression tests cho `/`, `///` và `  ///  `.
- Không thay đổi retry, authentication, payload hoặc response contract.

## Bằng chứng kiểm tra

- TDD test đỏ trước implementation: 3 case đều không raise.
- Targeted endpoint tests: **6 passed**.
- Full suite: **727 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái acceptance

Slice offline đã đạt. Live model-service smoke và production golden parity
vẫn chưa xác minh vì checkout không có endpoint, credential và production
catalog thật; không dùng fake HTTP để thay thế bằng chứng live.
