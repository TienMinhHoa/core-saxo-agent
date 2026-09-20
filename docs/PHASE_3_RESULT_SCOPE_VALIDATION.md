# Phase 3 — Xác minh phạm vi kết quả extraction

## Mục tiêu

Chặn kết quả extraction bị gắn nhầm vào document, source version hoặc model
profile của request hiện tại. Đây là một integrity boundary nhỏ ở application
workflow, trước khi API trả `PdfExtractionResult` cho caller.

## Thay đổi

- `ProcessDocument.execute()` vẫn đọc và kiểm tra kích thước cùng SHA-256 của
  source artifact trước khi gọi extractor.
- Sau khi extractor trả kết quả, workflow kiểm tra ba trường:
  `document_ref`, `source_version`, `model_profile` phải khớp request.
- Kết quả lệch phạm vi bị từ chối bằng `ValueError`; không có fallback và
  không trả kết quả cho route.
- Bổ sung ba contract cases độc lập cho từng trường lệch phạm vi.

## Bằng chứng kiểm thử

Chạy trong repository bằng `uv`:

```text
uv run pytest tests/test_phase_3_process_document.py
7 passed

uv run pytest
154 passed, 2 skipped, 1 warning

python -m compileall -q src
git diff --check
```

Hai test skip là dependency Gradio và sample source không có trong checkout;
không liên quan tới thay đổi này. Chưa thực hiện live model-service smoke hoặc
end-to-end persistence payload trong slice này.

## Giới hạn còn lại

`PdfExtractionResult` hiện chỉ mang `ArtifactRef`, chưa mang payload output;
vì vậy iteration này chưa thể tự ghi bytes Markdown/layout/manifest vào
`ArtifactRepository`. Slice kế tiếp cần chốt contract transfer/persistence của
output artifact trước khi tuyên bố process đã persist extraction end-to-end.
