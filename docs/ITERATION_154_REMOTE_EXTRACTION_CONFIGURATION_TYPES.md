# Iteration 154 - Kiểu runtime của cấu hình remote extraction

## Mục tiêu

Khóa một lát cắt nhỏ của Phase 3 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: constructor của
`RemotePdfExtractor` phải từ chối cấu hình `model` và `response_schema` sai kiểu
bằng lỗi hợp đồng rõ ràng, trước khi gọi `.strip()` hoặc chạm vào provider.

## Thay đổi

- Bổ sung kiểm tra `isinstance(value, str)` cho `model` và `response_schema`.
- Giữ nguyên hành vi canonical hóa bằng `strip()` cho chuỗi hợp lệ.
- Bổ sung regression test cho `None`, số nguyên và object tùy ý ở cả hai field.
- Không thay đổi transport, retry, response mapping hay fallback GPU/local.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_remote_pdf_extractor.py -q
21 passed
```

Kiểm tra này là offline; chưa chứng minh live model-service, credential, network
hay production catalog.
