# Iteration 284 - tagging dùng facade ingestion

## Phạm vi

Lát cắt này tiếp tục Phase 7 Cleanup và enforcement. Mục tiêu là giữ boundary
ổn định giữa tagging và ingestion: parser chỉ dùng hợp đồng công khai của
`saxophone.ingestion`, không phụ thuộc trực tiếp module triển khai `models`.

## Thay đổi

- `saxophone.tagging.parser` lấy `IngestionSourceChunk` từ facade
  `saxophone.ingestion`.
- Bổ sung AST contract test để phát hiện việc parser quay lại import
  `saxophone.ingestion.models`.
- Giữ nguyên kiểu dữ liệu và hành vi parse; thay đổi chỉ nằm ở import boundary.

## Bằng chứng kiểm chứng

- Trước thay đổi, contract test mới tái hiện đúng vi phạm: **1 failed, 39
  passed**.
- Sau thay đổi, targeted boundary: `uv run pytest
  tests/test_phase_7_dependency_enforcement.py -q` - **40 passed**.
- Full offline suite và compile/diff check được chạy sau khi hoàn tất lát cắt.
- Live model-service smoke và production golden parity chưa thể xác minh vì
  checkout không có endpoint, credential và catalog production được phê duyệt.

## Trạng thái

Boundary tagging -> ingestion đã được khóa bằng test nguồn. Stop condition toàn
bộ vẫn chưa đạt do các kiểm chứng live bên ngoài checkout còn thiếu.
