# Iteration 146 - Canonical metadata cho extraction

## Mục tiêu

Đảm bảo `PdfExtractionRequest` và `PdfExtractionResult` không nhận metadata
không ổn định trước khi đi vào remote adapter, persistence hoặc ingestion.

## Thay đổi

- Siết `_require_non_blank()` để từ chối leading/trailing whitespace, Unicode
  chưa chuẩn hóa NFC và ASCII control character/DEL.
- Áp dụng contract cho `source_version`, `correlation_id`, `model_profile` ở
  request và `source_version`, `model_profile` ở result.
- Bổ sung regression tests TDD cho cả ba dạng dữ liệu không canonical.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_3_extraction_contract.py`.
- Full suite: `uv run pytest --basetemp=.pytest-tmp`.
- Tĩnh: `uv run python -m compileall -q src tests` và `git diff --check`.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity
vẫn chưa thể chạy vì checkout chưa có endpoint, credential và production
catalog được phê duyệt.
