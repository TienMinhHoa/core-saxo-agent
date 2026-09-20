# Iteration 152 - Khóa model identity của remote extraction

## Mục tiêu

Giữ boundary `RemotePdfExtractor` fail-closed khi model service hoặc một
`ModelClient` implementation trả response từ model khác với model đã cấu hình.
`ModelClient` là protocol nên adapter không được giả định mọi implementation đều
đã kiểm tra identity.

## Thay đổi

- Bổ sung contract test với `response.model` khác model request.
- `RemotePdfExtractor` từ chối response model drift trước khi đọc artifact.
- Không fallback hoặc ánh xạ artifact từ response sai model.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_3_remote_pdf_extractor.py -q
14 passed
```

Kiểm thử offline không chứng minh live model-service, credential, network hay
production catalog; các kiểm thử live vẫn cần endpoint và quyền truy cập thật.
