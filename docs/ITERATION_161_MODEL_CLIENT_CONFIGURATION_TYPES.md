# Bằng chứng iteration 161 — kiểu dữ liệu cấu hình LiteLLM model client

## Phạm vi

Siết boundary constructor của `LiteLLMModelClient` để các cấu hình số không
được nhận chuỗi, boolean hoặc số không hữu hạn từ environment/composition root.
Mục tiêu là trả về `ValueError` rõ ràng thay vì để phép so sánh nội bộ phát sinh
`TypeError` hoặc vô tình coi `bool` là số.

## Thay đổi

- Thêm helper dùng chung để kiểm tra kiểu numeric, integer và finite.
- Áp dụng cho timeout, số lần thử, backoff, jitter, circuit-breaker threshold
  và cooldown.
- Thêm 10 regression tests TDD cho chuỗi và boolean ở từng trường cấu hình.

## Kiểm chứng

- Red test trước implementation: 8/10 case thất bại đúng vì contract cũ trả
  `TypeError` hoặc chấp nhận `bool`.
- Targeted sau implementation:
  `uv run pytest tests/test_phase_1_litellm_client.py -k configuration_types`
  — **10 passed**.
- Cần chạy full suite và static checks ở cuối iteration để xác nhận không có
  regression ngoài boundary này.

## Giới hạn bằng chứng

Đây là kiểm chứng offline. Live model-service smoke và production parity vẫn
chưa xác minh vì checkout chưa có endpoint, credential và catalog production.
