# Bằng chứng iteration 166 — contract bearer token của model client

## Phạm vi

`LiteLLMModelClient` không được nhận bearer token có ký tự điều khiển. CR, LF,
NUL và các control character khác có thể làm hỏng HTTP header hoặc tạo đường
ranh giới header ngoài ý muốn; đây là validation boundary trước provider I/O.

## Thay đổi

- Constructor fail-closed với bearer token chứa ký tự điều khiển ASCII.
- Bổ sung 3 regression cases cho LF, CR và NUL.
- Không thay đổi việc trim token hợp lệ ở đầu/cuối hoặc header Authorization.

## Kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_litellm_client.py -k
  "control_characters_in_bearer_token" --basetemp=.pytest-tmp` — **3 passed**.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi.

## Giới hạn

Đây là bằng chứng offline. Live model-service smoke và production parity vẫn
chưa xác minh vì checkout chưa có endpoint, credential và catalog production
thật.
