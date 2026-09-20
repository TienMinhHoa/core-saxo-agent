# Bằng chứng iteration 165 — kiểu response của HTTP transport

## Phạm vi

Khóa boundary async của `LiteLLMModelClient`: sau khi `http_client.post` được
`await`, transport phải trả về đúng `httpx.Response`. Nếu trả về object khác,
client phải fail-closed bằng lỗi contract rõ ràng trước khi đọc status hoặc JSON.

## Thay đổi

- Thêm kiểm tra runtime `isinstance(response, httpx.Response)` ngay sau `await`.
- Thêm regression test cho async transport trả về object sai kiểu.
- Bảo toàn contract hiện có cho synchronous result: vẫn từ chối vì không awaitable.

## Kiểm chứng

- Red test trước khi sửa đã tái hiện `AttributeError` khi dereference object sai kiểu.
- Targeted test sau sửa: `uv run pytest tests/test_phase_1_litellm_client.py -k "wrong_type or sync_transport" --basetemp=.pytest-tmp`.
- Full suite, `compileall` và `git diff --check` được chạy sau thay đổi.
- Đây là kiểm chứng offline với fake transport; live model-service smoke và production golden parity vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production.
