# Iteration 358 - khóa output conflict khi generation rỗng

## Phạm vi

Iteration này chỉ bổ sung một regression contract cho Phase 8 paragraph tagging.
Không thay đổi implementation trước khi có bước TDD tiếp theo được duyệt.

## Phát hiện

`TagConflictResolution` chỉ kiểm tra ánh xạ một-một khi `generated_tags` là giá trị
truthy. Vì vậy, một model response có `generated_tags=()` nhưng vẫn chứa
resolution có thể lọt qua domain contract và tạo tag ngoài kết quả generation.

## Thay đổi

Thêm test `test_empty_generation_cannot_return_conflict_resolutions` để khóa invariant:
generation rỗng phải có đúng zero resolution. Test hiện được viết trước implementation
theo TDD và đang cố ý đỏ cho đến khi validator được sửa ở iteration kế tiếp.

## Bằng chứng

Đã chạy:

```text
uv run pytest tests/test_phase_8_conflict_resolution_contract.py --basetemp=.pytest-tmp-358-phase8-contract
```

Kết quả dự kiến của slice TDD hiện tại: **1 failed, 5 passed**. Failure xác nhận
regression test tái hiện đúng lỗ hổng hiện tại; chưa tuyên bố Phase 8 đã hoàn tất.

Live model-service smoke và production parity vẫn chưa thể xác minh vì checkout
không có endpoint, credential và production catalog thật.
