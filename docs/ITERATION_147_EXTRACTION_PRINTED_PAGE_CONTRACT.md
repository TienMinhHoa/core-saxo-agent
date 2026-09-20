# Iteration 147 - Tách `printed_page` khỏi `page_index`

## Mục tiêu

Đáp ứng mục 13.3 của kế hoạch kiến trúc: locator extraction phải giữ riêng
chỉ số trang PDF và số trang in, không suy luận một giá trị từ giá trị còn lại.

## Thay đổi

- Bổ sung `ExtractionCoordinate.printed_page: int | None`.
- `printed_page` là tùy chọn vì tài liệu có thể không có số trang in hoặc chưa
  trích xuất được số đó.
- Khi có giá trị, contract chỉ chấp nhận số nguyên dương; từ chối `bool`, số
  thực, số 0 và số âm theo nguyên tắc fail-closed.
- `page_index` vẫn giữ nguyên semantics zero-based của trang PDF; hai trường
  tồn tại độc lập.

## Bằng chứng kiểm thử

- TDD targeted: `uv run pytest tests/test_phase_3_extraction_contract.py -q`
  đạt **48 passed**.
- Full suite: `uv run pytest --basetemp=.pytest-tmp -q` đạt kết quả được ghi
  ở phần bàn giao của iteration này.
- Kiểm tra cú pháp: `uv run python -m compileall -q src tests`.
- Kiểm tra whitespace diff: `git diff --check`.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity
chưa chạy vì checkout vẫn thiếu endpoint, credential và catalog production đã
được phê duyệt.
