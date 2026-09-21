# Iteration 364 - khóa thứ tự resolution của Phase 8

## Phạm vi

`TagConflictResolution` đã kiểm tra tập `generated_tags`, nhưng vẫn cho phép
resolver trả các resolution theo thứ tự khác với generator. Điều này làm
projection `TaggedParagraph.tags` thay đổi thứ tự một cách không xác định.

## Thay đổi

- Thêm regression test TDD trong
  `tests/test_phase_8_tag_paragraph_use_case.py` cho resolver đảo thứ tự
  resolution.
- Siết boundary `TagParagraph` trong
  `src/saxophone/tagging/use_cases.py`: thứ tự `resolution.generated_tag` phải
  khớp chính xác với `generated.tags`; nếu không, use case fail-closed.
- Không thay đổi source text, profile contract, hay transport/model adapter.

## Bằng chứng

- Test Phase 8: **7 passed**.
- Full suite: **1078 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt; chỉ còn cảnh báo chuyển LF/CRLF của Git trên hai
  file Python.
- Live model-service smoke và production parity chưa xác minh vì checkout
  không có endpoint, credential và production catalog thật.

## Kết luận

Projection tag của Phase 8 nay deterministic theo thứ tự generator và không
âm thầm chấp nhận resolver bị reorder.
