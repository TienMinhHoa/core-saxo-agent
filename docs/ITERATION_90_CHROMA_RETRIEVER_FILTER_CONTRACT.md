# Iteration 90 - Contract `filters` cho Chroma semantic retriever

## Phạm vi

Khóa projection `filters` của `ChromaSemanticRetriever.search` trước khi gọi
embedding provider hoặc Chroma. Theo contract Chroma trong kế hoạch kiến trúc,
`where` chỉ nhận mapping có key chuỗi không-blank và value scalar hữu hạn.

## Thay đổi

- Bổ sung validation fail-closed cho `filters` trước mọi provider I/O.
- Từ chối input không phải mapping, key blank, value list/nested object và số
  `NaN`/vô hạn.
- Giữ mapping rỗng khi không truyền filter và chuyển tiếp nguyên vẹn scalar hợp lệ.
- Bổ sung regression tests chứng minh input sai không gọi embedding, cùng test
  forwarding cho filter hợp lệ.

## Bằng chứng

- Targeted: `uv run pytest tests/test_chroma_semantic_retriever.py --basetemp=.pytest-tmp`
  - **28 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp`
  - **472 passed, 2 skipped, 1 warning**.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` - **đạt**.
- Không khởi chạy process nền; live model-service smoke và production golden
  parity vẫn chưa xác minh vì checkout thiếu endpoint, credential và catalog
  production thật.

## Trạng thái

Contract filter offline đã được khóa. Đây là validation boundary, không thay đổi
chiến lược ranking hay schema dữ liệu của Chroma.
