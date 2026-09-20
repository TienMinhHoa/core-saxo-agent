# Iteration 105 — document_ref không trở thành path tùy ý

## Phạm vi

Khóa `document_ref` tại hai API boundary tạo hoặc dùng artifact nguồn:

- `POST /api/v1/documents/{document_ref}/source`;
- `POST /api/v1/documents/{document_ref}/process`.

`document_ref` phải là một identity đơn, không chứa `/`, `\\`, `:`, NUL,
URL scheme/authority, hoặc khoảng trắng thừa. Nhờ vậy adapter artifact không
nhận một document reference có thể biến thành path traversal hoặc Windows drive
path. Policy nằm ở `documents.policies` và được route dùng chung.

## TDD và bằng chứng

- Viết regression test trước implementation: document ref `..\\outside` phải
  trả HTTP `422`, không gọi `ArtifactRepository.put`.
- Red trước sửa: test nhận HTTP `201`, chứng minh route cũ không có guard.
- Green sau sửa: targeted test `uv run pytest tests/test_phase_7_api_routes.py -q
  -k document_ref_that_could_escape_artifact_root`.
- Cần chạy full suite ở cuối iteration để kiểm tra compatibility.

## Giới hạn xác minh

Đây là policy bảo vệ path tại API boundary; không thay thế authorization hoặc
quyết định định dạng ID ở cấp sản phẩm. Live model-service smoke vẫn chưa thể
chạy vì checkout không có endpoint, credential và production catalog thật.
