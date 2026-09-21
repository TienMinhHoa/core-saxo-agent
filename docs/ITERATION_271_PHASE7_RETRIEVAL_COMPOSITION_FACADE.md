# Iteration 271 - Composition root dùng retrieval facade

## Phạm vi

Khóa một điểm bypass trong `saxophone.app.factory`: composition root không còn
import trực tiếp contract và use case từ các module triển khai của retrieval.

## Thay đổi

- `factory.py` lấy `ChunkRetriever` và `RetrieveEvidence` từ facade
  `saxophone.retrieval`.
- Thêm enforcement test để ngăn import trực tiếp
  `retrieval.models`, `retrieval.ports` và `retrieval.use_cases` quay lại trong
  composition root.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q` - **32 passed**.
- `uv run pytest -q` - **957 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` - đạt.
- `git diff --check` - đạt; chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên Windows.

## Giới hạn

Các adapter cụ thể vẫn được composition root import trực tiếp theo đúng quyền
sở hữu wiring; iteration này chỉ xử lý application contract/use-case của
retrieval.
