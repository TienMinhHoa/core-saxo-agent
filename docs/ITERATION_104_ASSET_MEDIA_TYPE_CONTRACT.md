# Iteration 104 — contract media type cho image asset

## Mục tiêu

Tiếp tục tiêu chí nghiệm thu về asset access trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
asset chỉ được phục vụ khi reference an toàn, artifact có `ArtifactKind.IMAGE` và
metadata khai báo đúng MIME type ảnh.

## Thay đổi

- Thêm policy dùng chung `is_image_media_type`, chấp nhận MIME type không phân biệt
  hoa thường và có tham số MIME hợp lệ.
- Asset API trả `422` trước khi đọc bytes nếu resolver trả artifact kind `IMAGE`
  nhưng media type không bắt đầu bằng `image/`.
- `RepositoryBackedImageArtifactGate` áp dụng cùng policy để đường kiểm tra ở
  application và đường API không bị lệch contract.
- Thêm regression test cho `application/octet-stream` giả danh image artifact.

## Bằng chứng xác minh

- `uv run pytest tests/test_phase_7_api_routes.py -q`: **27 passed**.
- `uv run pytest -q`: **497 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển đổi LF/CRLF của Git trên
  các file Python khi checkout Windows.

## Phạm vi chưa xác minh

Live model-service smoke và production parity chưa chạy được vì checkout hiện
chưa có endpoint, credential và catalog production thật. Stop condition toàn bộ
kiến trúc vì vậy chưa đạt.
