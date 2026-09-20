# Bằng chứng iteration 164 — contract async của HTTP transport

## Phạm vi

Iteration này tiếp tục siết boundary của `LiteLLMModelClient`. Iteration 163
đã kiểm tra `http_client.post` tồn tại và callable, nhưng một dependency đồng bộ
vẫn có thể lọt qua constructor rồi chỉ lỗi bằng `TypeError` khi request chạy.

## Thay đổi

- Kiểm tra kết quả trả về của `http_client.post` bằng `inspect.isawaitable` trước
  khi `await`.
- Nếu transport trả về response đồng bộ, adapter fail-closed bằng
  `ValueError("http_client.post must return an awaitable")`.
- Thêm regression test chứng minh sync transport không đi vào response mapping.

## Kiểm chứng

- Targeted: `uv run pytest tests/test_phase_1_litellm_client.py`.
- Full suite, compileall và `git diff --check` sẽ được chạy sau thay đổi.
- Đây vẫn là kiểm chứng offline bằng fake transport; live model-service smoke và
  production golden parity chưa thể xác minh vì checkout chưa có endpoint,
  credential và catalog production.
