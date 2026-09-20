# Bằng chứng capability health — Phase 7

## Phạm vi

Lát cắt này chuẩn hóa response của `GET /api/v1/health` theo mục 17.3 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:

- có trạng thái `app` và `model_service`;
- có trạng thái độc lập cho `extraction`, `ingestion`, `retrieval`, `chat`;
- không đưa bearer token hoặc secret vào response;
- giữ trường `remote_gpu` như compatibility field trong giai đoạn strangler
  migration.

## Bằng chứng

Contract test:

```text
tests/test_phase_7_api_routes.py::test_health_exposes_architecture_capabilities_without_provider_secrets
```

Test dùng fake gateway trả `ready` và capability `chat`, nên không cần gọi
remote GPU thật. Kết quả response xác nhận capability đã compose (`extraction`)
và capability chưa compose (`ingestion`, `retrieval`, `chat`) được công bố rõ
ràng; chuỗi `secret-token` không xuất hiện.

## Giới hạn xác minh

Đây là kiểm thử offline cho composition root và HTTP response. Nó không chứng
minh remote model service đang sẵn sàng, không thay thế live smoke test, và chưa
triển khai cache health probe cho production.
