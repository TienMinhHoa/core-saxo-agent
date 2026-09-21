# Iteration 365 - Bảo toàn provenance nguồn trong paragraph tagging

## Phạm vi

Phase 8 yêu cầu kết quả topic tagging không làm mất provenance của paragraph
nguồn. Slice này khóa projection từ `ParagraphBlock` sang `TaggedParagraph` và
round-trip của JSON sidecar; không thay đổi giao thức model-service hay chiến
lược lưu trữ vector.

## Thay đổi

- `TaggedParagraph` giữ `chunk_id`, `ordinal`, `heading_path`, `image_refs` và
  `image_captions`, đồng thời validate các invariant giống `ParagraphBlock`.
- `TagParagraph` sao chép nguyên trạng metadata nguồn vào projection sau khi
  generation và conflict resolution thành công.
- `JsonTaggedParagraphRepository` lưu và đọc lại toàn bộ metadata provenance,
  thay vì chỉ lưu text và tags.
- Bổ sung regression contract cho projection có heading/ảnh/caption và fixture
  persistence có metadata nguồn.

## Bằng chứng kiểm chứng

- Targeted Phase 8: `17 passed, 2 skipped`.
- Full suite với thư mục tạm trong workspace:
  `uv run pytest -q --basetemp=.pytest-tmp-365` -> `1079 passed, 18 skipped, 1 warning`.
- `uv run python -m compileall -q src` đạt.
- `git diff --check` đạt; cảnh báo còn lại chỉ là chuyển đổi LF/CRLF của Git trên
  Windows.

Lần chạy full suite đầu tiên dùng thư mục Temp mặc định và gặp `WinError 5`
  tại test atomic PDF state (`os.replace`). Chạy lại với `--basetemp` trong
  workspace đã xanh; đây là vấn đề quyền của thư mục Temp, không phải
  regression của slice tagging.

## Trạng thái và giới hạn

Slice này hoàn tất một phần exit criterion về bảo toàn source provenance ở
paragraph tagging. Live model-service smoke và production parity vẫn chưa thể
 xác minh vì checkout chưa có endpoint, credential và production catalog thật.
