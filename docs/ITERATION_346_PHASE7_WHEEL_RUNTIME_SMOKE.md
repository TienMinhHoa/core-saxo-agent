# Iteration 346 — smoke runtime từ wheel backend

## Phạm vi

Kiểm chứng artifact wheel được build ở Iteration 345 có thể cài vào một môi
trường Python sạch và quảng bá đúng console entrypoint `saxophone-api`. Đây là
bằng chứng đóng gói/runtime offline; không phải live smoke tới model-service.

## Bằng chứng

Đã chạy lần lượt:

```text
uv venv .pytest-tmp-346-wheel-smoke --python 3.12
uv pip install --python .pytest-tmp-346-wheel-smoke\Scripts\python.exe \
  .pytest-tmp-345-build\saxophone_rag_backend-0.1.0-py3-none-any.whl
```

Kết quả: cài thành công wheel và các dependency runtime, import được package
`saxophone` từ `site-packages`.

```text
.pytest-tmp-346-wheel-smoke\Scripts\saxophone-api.exe --help
```

Kết quả: console script khởi chạy thành công và hiển thị các option `--host`
và `--port`.

## Lưu ý kiểm thử

Một lần thử `uv pip install --no-deps` cố ý không cài dependency đã thất bại
với `ModuleNotFoundError: fastapi`. Đây là kết quả đúng của phép thử thiếu
dependency, không phải lỗi metadata wheel. Cài wheel theo metadata dependency
đã khắc phục và smoke thành công.

## Kết luận

Tiêu chí Phase 7 về khả năng cài đặt và khởi chạy entrypoint backend từ wheel
đã có thêm bằng chứng offline. Live model-service smoke và production golden
parity vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và
production catalog thực tế.
