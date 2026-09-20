# Iteration 149 — khóa source version ở biên remote extraction

## Phạm vi

Chọn hướng Clean Code: củng cố một integrity boundary nhỏ trong
`RemotePdfExtractor`. Kết quả từ model service chỉ được map thành
`PdfExtractionResult` khi `source_version` trong response khớp chính xác với
source version của request hiện tại.

## Thay đổi

- Bổ sung regression test cho response trả về source version của tài liệu khác.
- `RemotePdfExtractor` fail-closed trước khi map artifact nếu source version bị
  lệch; không fallback và không phát sinh kết quả extraction sai phạm vi.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_3_remote_pdf_extractor.py`
- Full suite: `uv run pytest --basetemp=.pytest-tmp`
- Static: `uv run python -m compileall -q src tests`
- Hygiene: `git diff --check`

Live model-service smoke và production golden parity chưa chạy vì checkout
không có endpoint, credential và production catalog thật.
