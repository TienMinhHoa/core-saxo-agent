# Phase 3 — Adapter extraction PDF từ model service

## Phạm vi iteration 23

Chọn hướng Clean Code: tách cổng `PdfExtractor` khỏi transport/provider và triển khai
`RemotePdfExtractor` dùng `ModelClient` đã có. Slice này chưa wiring FastAPI route hay
workflow persistence; mục tiêu là khóa biên async và mapping kết quả trước khi nối vào
composition root.

## Thay đổi

- `PdfExtractor` là async port nhận `PdfExtractionRequest` và trả `PdfExtractionResult`.
- `RemotePdfExtractor` tạo `ModelRequest` với task `pdf_extract`, truyền document/source
  identity, source version, correlation ID và model profile.
- Adapter chỉ chấp nhận đúng task/schema và yêu cầu đủ ba `ArtifactRef`: markdown, layout,
  extraction manifest. Sai payload bị fail rõ ràng, không fallback im lặng.
- Không import Paddle, CUDA, FastAPI hay filesystem path vào extraction adapter.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_3_remote_pdf_extractor.py tests/test_phase_3_extraction_contract.py --basetemp=.pytest-tmp`: **11 passed**.
- `uv run pytest --basetemp=.pytest-tmp`: **138 passed, 2 skipped**, 1 warning.
- Hai test skip là môi trường: thiếu Gradio và thiếu sample source; không liên quan slice này.
- `python -m compileall -q src`: kiểm tra cú pháp thành công.
- `git diff --check`: không phát hiện whitespace error.

## Ranh giới còn lại

Adapter chưa được gắn vào `AppContainer`, chưa có HTTP extraction route và chưa commit artifact
qua workflow. Đây là bước kế tiếp sau khi contract này được giữ ổn định.
