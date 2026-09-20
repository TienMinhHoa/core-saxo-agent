# Bằng chứng iteration 167 — contract endpoint của model client

## Phạm vi

`LiteLLMModelClient` nhận endpoint từ composition root và dùng endpoint này trong
HTTP transport. Endpoint chứa CR, LF, NUL hoặc control character khác không phải
là cấu hình URL an toàn; boundary cần fail-closed trước provider I/O.

## Thay đổi

- Constructor từ chối endpoint chứa ASCII control character, cùng quy tắc với
  bearer token.
- Bổ sung 3 regression cases cho LF, CR và NUL.
- Không thay đổi hành vi endpoint hợp lệ: vẫn trim khoảng trắng đầu/cuối và
  trailing slash như trước.

## Kiểm chứng

- TDD red trước implementation: 3 test mới failed vì constructor chưa có guard.
- Targeted sau implementation: `uv run pytest tests/test_phase_1_litellm_client.py
  -k endpoint --basetemp=.pytest-tmp` — **3 passed**.
- Full suite, compileall và `git diff --check` được chạy sau thay đổi.

## Giới hạn

Đây là bằng chứng offline. Live model-service smoke và production parity vẫn chưa
xác minh vì checkout chưa có endpoint, credential và production catalog thật.
