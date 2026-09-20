# Bằng chứng iteration 162 – kiểm tra dependency được inject của LiteLLM model client

## Phạm vi

Siết boundary constructor của `LiteLLMModelClient` để hai dependency dùng cho
retry và circuit-breaker là callable thật sự:

- `jitter_source` phải gọi được để sinh jitter retry;
- `monotonic_clock` phải gọi được để đo thời gian và mở/đóng circuit-breaker.

Nếu truyền nhầm object, constructor trả `ValueError` ngay thay vì để lỗi xảy ra
muộn trong request runtime.

## Kiểm thử TDD

- Red trước implementation: 2 case mới đều thất bại vì constructor cũ chấp nhận
  object không callable.
- Green sau implementation:
  `uv run pytest tests/test_phase_1_litellm_client.py -k "injected_dependencies or configuration_types"`
  → **12 passed**.

## Kết luận và giới hạn

Contract dependency injection đã được kiểm chứng offline. Live model-service
smoke và production golden parity vẫn chưa xác minh vì checkout chưa có endpoint,
credential và catalog production thật.
