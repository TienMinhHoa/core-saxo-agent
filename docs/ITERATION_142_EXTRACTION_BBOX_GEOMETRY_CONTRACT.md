# Iteration 142 - Contract hình học bbox của extraction

## Mục tiêu

Đồng bộ contract `ExtractionCoordinate.bbox` với canonicalizer layout OCR:
tọa độ phải tạo thành một hình chữ nhật có chiều rộng và chiều cao dương.

## Thay đổi

- `ExtractionCoordinate` tiếp tục từ chối giá trị không hữu hạn, boolean và tọa độ âm.
- Bổ sung kiểm tra `right > left` và `bottom > top`.
- Bổ sung test TDD cho bbox có cạnh bằng nhau và bbox bị đảo chiều.

Điều này ngăn locator rỗng hoặc hình học đảo chiều đi qua application boundary,
trước khi được persist hoặc dùng để render overlay.

## Bằng chứng kiểm thử

- TDD đỏ trước khi sửa: 3 test mới thất bại vì DTO còn chấp nhận bbox suy biến.
- Sau khi sửa: `uv run pytest tests/test_phase_3_extraction_contract.py -q` đạt.
- Đã chạy thêm full suite, `compileall` và `git diff --check` sau thay đổi.

## Giới hạn xác minh

Đây là xác minh offline/static. Live model-service smoke và production golden
parity vẫn cần endpoint, credential và catalog production thật.
