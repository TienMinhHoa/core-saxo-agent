# Iteration 153 - Chuẩn hóa cấu hình remote extraction

## Mục tiêu

Đảm bảo `RemotePdfExtractor` dùng cùng một giá trị canonical cho `model` và
`response_schema` ở constructor, request gửi tới model service và bước kiểm tra
response. Trước thay đổi, request DTO tự trim nhưng adapter giữ chuỗi cấu hình
thô; cấu hình có khoảng trắng đầu/cuối vì vậy có thể bị từ chối sai khi đối
chiếu model/schema.

## Thay đổi

- `RemotePdfExtractor` trim và lưu `model`, `response_schema` sau khi đã kiểm tra
  không rỗng.
- Bổ sung regression test chứng minh request canonical và response hợp lệ được
  map thành công với cấu hình có khoảng trắng biên.
- Không thay đổi transport, retry, artifact transfer hay fallback GPU/local.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_remote_pdf_extractor.py -q
15 passed
```

Kiểm thử offline không chứng minh live model-service, network, credential hay
production catalog. Các kiểm tra live vẫn cần endpoint và quyền truy cập thật.
