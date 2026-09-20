# Bằng chứng iteration 130 — kiểm tra đầy đủ image media type

## Phạm vi

Tiếp tục harden hợp đồng `ArtifactRef` trong Phase 2. Helper
`is_image_media_type` được dùng ở boundary phục vụ asset/image, vì vậy không
được chỉ nhìn tiền tố `image/` rồi chấp nhận chuỗi MIME malformed.

## Thay đổi

- `is_image_media_type` tái sử dụng `is_safe_media_type` trước khi phân loại
  type chính là `image/*`.
- Bổ sung regression test cho quoted parameter chứa dấu chấm phẩy hợp lệ.
- Bổ sung regression test fail-closed cho parameter rỗng, quoted value chưa
  đóng và type chính có phần dư không hợp lệ.

## Kiểm chứng

- `uv run pytest tests/test_phase_2_artifact_reference_contract.py -q`: **62
  passed**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên
  Windows.

## Giới hạn còn lại

Live model-service smoke và production golden parity chưa chạy được vì
checkout hiện thiếu endpoint, credential và catalog production được phê duyệt.

