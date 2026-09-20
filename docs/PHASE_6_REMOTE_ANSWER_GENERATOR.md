# Phase 6 — RemoteAnswerGenerator

## Phạm vi iteration 16

Lát cắt này nối `AnswerGenerator` của module Chat với port `ModelClient` dùng
chung. Adapter chỉ chuyển đổi `EvidenceBundle` đã được validate thành
`ModelRequest` task `answer_generate`, rồi chuyển `ModelResponse` thành
`GeneratedAnswer`. Adapter không biết HTTP, LiteLLM SDK, Chroma hay FastAPI.

## Quyết định Clean Code

- `RemoteAnswerGenerator` nằm ở application adapter của Chat và phụ thuộc vào
  `ModelClient` protocol của platform.
- Prompt/input boundary gửi question, retrieval version, selected chunk refs,
  source texts và image refs; không gửi database client hay filesystem path.
- Response phải đúng task và response schema trước khi tạo `GeneratedAnswer`.
- `answer`, `token_usage` và `cost` được kiểm tra qua DTO `GeneratedAnswer`;
  output malformed bị từ chối, không có fallback im lặng.
- Model version lấy từ response đã validate; không expose chain-of-thought.

## Bằng chứng kiểm thử

Test mới tại `tests/test_remote_answer_generator.py` bao phủ:

1. Mapping request/response hợp lệ và giữ nguyên evidence đã chọn.
2. Từ chối response sai task.
3. Từ chối `token_usage` sai kiểu.

Lệnh xác minh trong iteration:

```text
uv run pytest tests/test_remote_answer_generator.py -q
3 passed
```

## Giới hạn còn lại

Chưa có adapter HTTP/LiteLLM thật và chưa wiring adapter vào composition root;
đây là lát cắt contract/application adapter, không phải live provider smoke test.
