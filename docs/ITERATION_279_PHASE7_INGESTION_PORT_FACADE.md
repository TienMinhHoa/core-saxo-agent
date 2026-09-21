# Iteration 279 - facade cho port tái sử dụng embedding

## Phạm vi

Composition root đã dùng facade `saxophone.ingestion` cho các contract
embedding và indexing, nhưng vẫn import `EmbeddingReuseStore` trực tiếp từ
`saxophone.ingestion.ports`. Slice này hoàn tất cùng một boundary cho port còn
lại; không thay đổi hành vi lưu cache embedding hay pipeline ingestion.

## Thay đổi

- Export `EmbeddingReuseStore` từ `saxophone.ingestion`.
- Chuyển type import trong `saxophone.app.factory` sang facade công khai.
- Mở rộng contract test facade để ngăn việc xoá export hoặc quay lại import
  implementation module.

## Bằng chứng kiểm tra

- Contract Phase 7: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`
  đạt sau thay đổi.
- Full suite: `uv run pytest -q` đạt sau thay đổi.
- `python -m compileall -q src tests` đạt.
- `git diff --check` không phát hiện whitespace lỗi.
- Live model-service smoke và production golden parity vẫn chưa thể xác minh
  vì checkout không có endpoint, credential và catalog production thật.
