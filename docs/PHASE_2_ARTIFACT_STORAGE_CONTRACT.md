# Phase 2 — Contract lưu artifact immutable

## Phạm vi iteration 3

Iteration này hoàn thiện lát cắt nhỏ còn thiếu của Phase 2: application có
`ArtifactRepository` port và adapter filesystem local an toàn. Chưa thay thế
các pipeline legacy, chưa thêm remote object storage và chưa kết nối adapter
vào FastAPI composition root.

## Quyết định Clean Code

- `saxophone.documents.ports.ArtifactRepository` chỉ mô tả use-case cần: ghi
  và đọc bytes theo `ArtifactRef`; application không biết filesystem.
- `saxophone.platform.artifacts.LocalArtifactRepository` là adapter đầu tiên,
  chạy blocking filesystem I/O trong `asyncio.to_thread` để không khóa event
  loop.
- Đường dẫn được tạo từ `artifact_id/version`, từ chối absolute path và `..`,
  đồng thời kiểm tra lại path đã resolve vẫn nằm dưới artifact root.
- Payload phải khớp `size_bytes` và SHA-256 đã khai báo trước khi ghi.
- Ghi dùng temporary file cùng thư mục, `flush` + `fsync`, sau đó
  `os.replace`; lỗi sẽ dọn temporary file và không để lại file `.tmp`.

## Bằng chứng kiểm thử

Contract test tại `tests/test_phase_2_artifact_storage_contract.py` bao phủ:

1. round-trip bytes qua `ArtifactRepository`;
2. từ chối payload sai kích thước;
3. từ chối artifact id có path traversal;
4. ghi atomic không để lại temporary file.

Lệnh và kết quả:

```text
uv run pytest tests/test_phase_2_artifact_storage_contract.py -q
4 passed in 0.13s
```

## Trạng thái so với kế hoạch

Đơn vị này đáp ứng phần “chuyển safe paths/atomic writes vào platform
policies” của Phase 2. Exit criteria về Chroma adapter, metadata repository,
model gateway và tích hợp workflow vẫn chưa hoàn tất; iteration sau nên tiếp
tục bằng một contract nhỏ độc lập thay vì nối adapter này vào production flow
ngay lập tức.
