# Iteration 148 - Kiểm tra runtime type cho artifact extraction

## Mục tiêu

Tiếp tục thực hiện contract extraction trong mục 13.3 của kế hoạch kiến trúc:
DTO ở boundary phải fail-closed và trả lỗi domain rõ ràng khi nhận dữ liệu sai
kiểu, thay vì để lỗi nội bộ rò ra từ provider hoặc thuộc tính Python.

## Thay đổi

- `PdfExtractionRequest` dùng chung kiểm tra `source` là `ArtifactRef` trước khi
  kiểm tra `ArtifactKind.SOURCE_PDF`.
- `PdfExtractionResult` áp dụng cùng kiểm tra cho `markdown`, `layout` và
  `manifest`.
- Input dạng `dict` hoặc object khác `ArtifactRef` nay trả `ValueError` có tên
  field (`<field> must be an ArtifactRef`), không còn gây `AttributeError` khi
  truy cập `.kind`.
- Giữ nguyên contract kind cụ thể; source vẫn phải là `source_pdf`, còn output
  vẫn phải lần lượt là markdown, layout và extraction manifest.

## Bằng chứng kiểm thử

- TDD targeted: `uv run pytest tests/test_phase_3_extraction_contract.py -q`
  đạt **52 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp -q` đạt **659 passed, 3
  skipped, 1 warning**.
- Kiểm tra cú pháp: `uv run python -m compileall -q src tests` đạt.
- Kiểm tra whitespace: `git diff --check` đạt.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity
chưa thực hiện vì checkout vẫn thiếu endpoint, credential và catalog production
được phê duyệt.
