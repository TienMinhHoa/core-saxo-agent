# Iteration 79 — Hợp đồng embedding dimension của Chroma

## Phạm vi

Tiếp tục siết một điểm vào nhỏ của `ChromaVectorIndex`: cấu hình
`embedding_dimension` phải là số nguyên dương thực sự trước khi adapter tạo
bounded I/O limiter hoặc sử dụng provider.

## Thay đổi

- Từ chối `bool`, số thực, chuỗi, số không và số âm.
- Giữ `None` là giá trị hợp lệ để tương thích với collection không khai báo
  dimension tại composition root.
- Dùng lỗi `ValueError` thống nhất thay vì để phép so sánh kiểu sai phát sinh
  `TypeError`.

## Bằng chứng kiểm thử

- TDD: thêm test `test_chroma_index_rejects_malformed_embedding_dimension` với
  các giá trị `0`, `-1`, `True`, `1.5` và `"3"`.
- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -k
  "malformed_embedding_dimension or chroma_search" -q` → **15 passed**.
- Full suite: `uv run pytest -q` → **437 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt; chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên
  Windows, không có whitespace error.

## Liên hệ kiến trúc

Điều chỉnh này thực thi yêu cầu adapter phải validate dimension trước khi gọi
Chroma và bảo vệ contract vector dimension trong Phase 2/4 của kế hoạch
refactor. Chưa có live model-service smoke vì checkout vẫn không có endpoint,
credential và catalog production.
