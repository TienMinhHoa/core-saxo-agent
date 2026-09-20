# Iteration 143 — Contract kiểu runtime cho ExtractionCoordinate

## Mục tiêu

Tiếp tục harden boundary extraction sau khi bbox đã được kiểm tra finite và có
hình học hợp lệ. DTO phải từ chối sớm kiểu dữ liệu sai thay vì để phép so sánh
phát sinh `TypeError` hoặc để `bool` (vốn là subclass của `int`) lọt vào.

## Thay đổi

- `ExtractionCoordinate` yêu cầu `coordinate_space` là một giá trị
  `CoordinateSpace` thật.
- `page_index`, `markdown_line_start` và `markdown_line_end` phải là `int`,
  đồng thời từ chối `bool`.
- Bổ sung test regression cho enum dạng chuỗi, số thực và boolean.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_3_extraction_contract.py`.
- Full suite: sẽ chạy trong iteration này bằng workspace basetemp để tránh
  lỗi quyền thư mục Temp của Windows.
- Kiểm tra tĩnh: `uv run python -m compileall -q src tests` và
  `git diff --check`.

Các kiểm tra trên là offline; live model-service smoke và production golden
parity vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và
production catalog thật.
