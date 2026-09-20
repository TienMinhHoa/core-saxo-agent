# Iteration 151 - Kiểm tra kiểu response của remote extraction

## Mục tiêu

Khóa boundary của `RemotePdfExtractor` để dữ liệu trả về từ model client sai
kiểu bị từ chối rõ ràng trước khi truy cập thuộc tính hoặc đọc artifact.

## Thay đổi

- `RemotePdfExtractor` xác nhận response thực sự là `ModelResponse` trước khi
  đọc `task`, `response_schema`, `source_version` và `output`.
- `_required_artifact` xác nhận output là mapping trước khi gọi `.get()`;
  contract này fail-closed nếu helper bị gọi với dữ liệu runtime không đúng.
- Bổ sung regression tests cho response object sai kiểu và output không phải
  mapping; provider contract hiện có vẫn được giữ nguyên.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_remote_pdf_extractor.py -q
13 passed
```

Kiểm thử offline này không chứng minh live model-service, credential, network
hay production catalog. Các kiểm tra live đó vẫn cần endpoint và quyền truy cập
thật.
