# Iteration 13 — Retry network failure của LiteLLM client

## Phạm vi

Lát cắt này hoàn thiện một phần hợp đồng retry trong mục 12 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: lỗi network/timeout được retry theo
backoff local, không phụ thuộc vào một HTTP response chưa tồn tại.

## Thay đổi

- `LiteLLMModelClient._post_with_retry` khởi tạo delay bằng local backoff cho
  mỗi attempt.
- Chỉ đọc `Retry-After` khi request đã nhận được HTTP response; lỗi
  `httpx.RequestError` dùng local backoff và không gây `UnboundLocalError`.
- Bổ sung contract test: timeout lần đầu, request lần hai thành công, số attempt
  và delay được kiểm chứng.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_litellm_client.py
uv run python -m compileall -q src tests
git diff --check
```

Các lệnh trên là kiểm tra cần chạy sau khi thay đổi. Live model-service smoke
vẫn chưa thể xác minh vì checkout chưa có endpoint và credential thật.

Kết quả thực tế của iteration này:

```text
tests/test_phase_1_litellm_client.py: 16 passed
uv run pytest -q: 291 passed, 2 skipped, 1 warning
compileall: passed
git diff --check: passed
```

## Giới hạn

Lát cắt này không giả lập hay tuyên bố production/live provider parity; retry
chỉ được chứng minh bằng HTTP mock và contract test offline.
