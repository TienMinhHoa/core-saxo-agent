# Iteration 144 - Bất biến hóa bbox của tọa độ extraction

## Mục tiêu

Tiếp tục siết hợp đồng `ExtractionCoordinate` theo kiến trúc Clean Code: DTO đã
`frozen` thì container `bbox` cũng phải là `tuple`, không được nhận `list` có
thể bị thay đổi sau khi khởi tạo.

## Thay đổi

- `ExtractionCoordinate` từ chối `bbox` không phải `tuple` bằng lỗi
  `ValueError` rõ ràng.
- Giữ nguyên các kiểm tra đã có: đúng bốn tọa độ, số hữu hạn, không âm và có
  chiều rộng/chiều cao dương.
- Bổ sung regression test chứng minh `list` bị từ chối trước khi có xử lý
  geometry.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_3_extraction_contract.py`
- Full suite: chạy lại `uv run pytest --basetemp=.pytest-tmp`.
- Chất lượng tĩnh: `uv run python -m compileall -q src tests` và
  `git diff --check`.

## Giới hạn xác minh

Đây là kiểm thử offline. Live model-service smoke và production golden parity
chưa thể chạy vì checkout hiện chưa có endpoint, credential và catalog production
được phê duyệt.
