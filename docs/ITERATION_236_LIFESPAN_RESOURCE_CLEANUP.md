# Iteration 236 - lifespan luôn đóng HTTP client khi cleanup vector index lỗi

## Phạm vi

FastAPI lifespan sở hữu cả vector index và HTTP client dùng chung cho remote
gateway/model client. Trước thay đổi này, nếu cleanup vector index ném lỗi thì
luồng shutdown dừng trước `http_client.aclose()`, làm rò rỉ tài nguyên mạng.

## Thay đổi

- Bọc cleanup vector index trong `try/finally` tại composition root.
- Đảm bảo `http_client.aclose()` luôn được gọi khi HTTP client do app tạo ra,
  kể cả khi `aclose()` hoặc `close()` của vector index thất bại.
- Thêm regression test chứng minh lỗi cleanup vẫn được phát ra nhưng HTTP
  client đã đóng.

## Bằng chứng kiểm thử

- Trước implementation: regression test thất bại vì `client.is_closed` vẫn là
  `False` sau lỗi `vector cleanup failed`.
- Targeted sau implementation: `2 passed, 1 warning` với:
  `uv run pytest tests/test_phase_1_composition_root.py::test_lifespan_closes_shared_http_client_when_vector_cleanup_fails tests/test_phase_1_composition_root.py::test_default_composition_owns_one_http_client_and_closes_it_with_lifespan -q --basetemp=.pytest-tmp`.
- Full suite: `920 passed, 18 skipped, 1 warning` với `uv run pytest -q
  --basetemp=.pytest-tmp`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.
- Thư mục tạm `.pytest-tmp` đã được xoá sau kiểm thử.

## Đối chiếu kiến trúc

Thay đổi củng cố yêu cầu async lifecycle trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: graceful shutdown phải giải
phóng các resource đã được composition root sở hữu, không phụ thuộc vào việc
cleanup của một adapter khác có thành công hay không.

## Giới hạn xác minh

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout không có endpoint, credential và production catalog thật.
