# Bằng chứng Iteration 133 — document reference trong ingestion

## Phạm vi

Đồng nhất policy `is_safe_document_reference` với các DTO ingestion. Trước
thay đổi, các DTO này chỉ kiểm tra chuỗi không-blank; vì vậy path traversal,
dấu `/`, control character hoặc Unicode chưa chuẩn NFC có thể lọt qua boundary
application dù extraction đã fail-closed.

## Thay đổi

- `IngestionCommand`, `IngestionSourceChunk`, `IndexInputRecord`,
  `IngestionReport` và `ChunkIndexRecord` cùng áp dụng policy document reference
  dùng chung.
- Bổ sung regression test cho traversal, slash, newline và Unicode decomposed
  trên toàn bộ năm DTO.
- Không thay đổi format của document reference hợp lệ; chỉ siết input không an
  toàn tại boundary.

## Kiểm chứng

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q
  --basetemp=.pytest-tmp` → **93 passed**.
- Full offline suite: `uv run pytest -q --basetemp=.pytest-tmp-133` →
  **585 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt.

Skip hiện hữu: Gradio/sample source không có và symbolic-link test thiếu quyền
Windows. Không có live model-service smoke trong iteration này vì checkout vẫn
thiếu endpoint, credential và production catalog được phê duyệt.
