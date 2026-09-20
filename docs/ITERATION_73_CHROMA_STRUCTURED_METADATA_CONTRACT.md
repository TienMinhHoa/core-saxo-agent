# Iteration 73 - Contract metadata có cấu trúc khi ghi Chroma

## Phạm vi

Khóa một lỗi tại boundary `ChromaVectorIndex`: pipeline ingestion tạo metadata
dạng `tuple` cho `tags` và `tagged_paragraph_ids`, trong khi Chroma yêu cầu
danh sách (`list`) cho metadata dạng nhiều giá trị.

## Thay đổi

- Thêm test round-trip với metadata tuple trong
  `tests/test_phase_1_chroma_live_contract.py`.
- Adapter chuyển tuple/list lồng nhau thành list trước khi gọi Chroma;
  metadata scalar và các trường provenance bắt buộc vẫn giữ nguyên.
- Kết quả đọc lại giữ nguyên nội dung có cấu trúc dưới dạng list mà downstream
  hiện tại đã hỗ trợ.

## Bằng chứng kiểm chứng

- TDD red: test mới thất bại tại Chroma SDK vì tuple không phải metadata value
  hợp lệ.
- TDD green: test round-trip mới đạt `1 passed`.
- Regression: `uv run pytest` đạt **421 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` đạt.
- `git diff --check` đạt.

## Trạng thái còn lại

Đây là kiểm chứng offline với Chroma persistent local. Live model-service smoke,
production catalog parity và deployment vẫn chưa được xác minh vì checkout chưa
có endpoint/credential production.
