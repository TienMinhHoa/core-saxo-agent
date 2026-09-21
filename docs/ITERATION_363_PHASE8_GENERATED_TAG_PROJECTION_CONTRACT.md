# Iteration 363 — khóa projection generated tags ở orchestration Phase 8

## Phạm vi

Iteration này xử lý một slice nhỏ còn thiếu trong Phase 8: `TagParagraph` phải
fail-closed nếu kết quả conflict-resolution không mang đúng tập `generated_tags`
mà generator đã trả về. Trước thay đổi, điều kiện kiểm tra chỉ chạy khi danh
sách resolution có giá trị truthy; payload rỗng vì vậy có thể đi tiếp và tạo
`TaggedParagraph` từ một mapping không còn chứng minh được nguồn tag.

## Thay đổi

- Thêm regression test TDD trong `tests/test_phase_8_tag_paragraph_use_case.py`
  với resolver trả về `generated_tags=()` dù generator đã sinh hai tag.
- Đổi boundary trong `src/saxophone/tagging/use_cases.py` từ kiểm tra có điều
  kiện sang so sánh chính xác: resolution phải có `generated_tags` bằng đúng
  `generated.tags`, kể cả trường hợp rỗng.
- Không thay đổi source text, profile validation, hay contract của remote
  adapter.

## Bằng chứng

- Trước khi sửa implementation: test mới đỏ đúng kỳ vọng, **1 failed, 5
  passed**.
- Sau khi sửa implementation: targeted test Phase 8 đạt **21 passed**.
- Full suite đạt **1077 passed, 18 skipped, 1 warning**; `compileall` và
  `git diff --check` đều thành công.
- Live model-service smoke và production parity chưa thể xác minh vì checkout
  không có endpoint, credential và production catalog thật.

## Kết luận

Invariant projection của Phase 8 hiện fail-closed tại cả model adapter và
application orchestration boundary; không có silent fallback khi resolution
thiếu liên kết với generation.
