# Iteration 22 - Wiring sink observability production

## Phạm vi

Lát cắt này hoàn thiện phần còn thiếu sau Iteration 21: event structured đã
được phát từ `LiteLLMModelClient`, nhưng composition root chưa có sink mặc định
để đưa event vào logging boundary của ứng dụng.

## Thay đổi

- Thêm `LoggingEventSink`, dùng standard-library `logging` và chỉ ghi
  `StructuredEvent.as_dict()` qua trường `structured_event`.
- Không ghi prompt, response, bearer token, API key hoặc payload tùy ý vào log.
- `create_app` mặc định tạo một sink và truyền cùng sink đó vào
  `LiteLLMModelClient`; sink cũng được giữ trong `AppContainer` để kiểm tra
  dependency graph rõ ràng.
- Cho phép `AppOverrides.event_sink` thay thế sink trong test hoặc deployment
  adapter khác mà không đổi application code.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_observability_contract.py tests/test_phase_1_composition_root.py -q
28 passed, 1 warning

python -m compileall -q src tests
Đạt

git diff --check
Đạt (chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên Windows)
```

Test mới kiểm tra event được log với các field allowlist và xác nhận default
composition inject đúng sink vào model client.

## Giới hạn còn lại

- Chưa chạy live model-service smoke: checkout chưa được cung cấp endpoint,
  credential và production catalog.
- Sink hiện dùng standard logging; metrics backend hoặc log collector cụ thể
  là quyết định triển khai riêng, không được giả định trong backend.
