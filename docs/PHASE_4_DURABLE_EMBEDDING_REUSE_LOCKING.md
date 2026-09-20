# Phase 4 — khóa ghi durable embedding reuse

## Mục tiêu

Đóng lát cắt còn thiếu sau `PHASE_4_DURABLE_EMBEDDING_REUSE_COMPOSITION`: hai
process có thể cùng cập nhật `embedding-reuse.json` mà không làm mất bản ghi của
nhau. Đây là biện pháp trực tiếp cho rủi ro request/model chạy trùng và ghi đè
cache đã được nêu trong mục 25.9 của solution architecture.

## Thay đổi

- `FileEmbeddingReuseStore` tạo lock file cạnh JSON cache.
- `find()` khóa trong lúc đọc; `save()` khóa toàn bộ chu kỳ đọc-gộp-ghi.
- Dùng file lock của hệ điều hành (`msvcrt` trên Windows, `fcntl` trên POSIX),
  vẫn giữ ghi file tạm rồi `os.replace()` để bảo toàn atomic replacement.
- Lock file không chứa dữ liệu ứng dụng; cache JSON vẫn là payload duy nhất được
  parse và validate.

## Bằng chứng kiểm thử

- Contract test `test_file_embedding_reuse_store_serializes_concurrent_writers`
  chạy hai instance đồng thời và xác nhận cả `chunk-1` lẫn `chunk-2` còn tồn tại.
- Nhóm test adapter: `3 passed`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển dòng LF/CRLF của Git trên
  Windows, không có whitespace error.

## Ranh giới còn lại

Đây là khóa file ở mức process trên một filesystem dùng chung. Chưa có live
model-service/Chroma smoke test và chưa chứng minh locking khi nhiều host ghi
qua filesystem phân tán; các mục đó vẫn cần kiểm tra riêng trước khi tuyên bố
nghiệm thu toàn bộ kiến trúc.
