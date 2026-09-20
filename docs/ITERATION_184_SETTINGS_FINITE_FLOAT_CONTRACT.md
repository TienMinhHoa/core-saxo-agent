# Iteration 184 - Cấu hình số thực phải hữu hạn

## Phạm vi

Theo `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, composition root phải fail-fast
khi cấu hình timeout, cache hoặc retry không hợp lệ. Parser cũ chỉ kiểm tra dấu
`< 0`/`<= 0`, nên `nan`, `inf` và số tràn như `1e999` có thể lọt qua.

## Thay đổi

- `_parse_non_negative_float` nay yêu cầu giá trị sau khi parse phải là số hữu hạn
  bằng `math.isfinite`.
- Quy tắc áp dụng đồng nhất cho health-cache, health-timeout, LiteLLM timeout,
  retry backoff và các cấu hình số thực dùng chung parser.
- Bổ sung regression tests cho `nan`, `inf`, `-inf` và số tràn.

## Bằng chứng xác minh

- `uv run pytest -q tests/test_phase_1_settings.py`: **36 passed**.
- `uv run pytest -q`: **754 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo line-ending CRLF của Git trên Windows.

## Giới hạn

Đây là kiểm chứng offline với cấu hình và fake dependencies. Live model-service
smoke và production parity vẫn chưa thể xác minh vì checkout chưa có endpoint,
credential và catalog production thật.
