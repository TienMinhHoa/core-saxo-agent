# Iteration 330 - policy path artifact PDF duy nhất

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: job store phải là
ranh giới sở hữu policy artifact, còn workflow và HTTP interface không nên phụ
thuộc vào nhiều helper path công khai trùng lặp.

## Thay đổi

- Xóa bốn helper path dư thừa khỏi `PdfLayoutJobStore`:
  `source_pdf_path`, `pages_dir`, `layout_dir`, `extraction_dir`.
- Giữ `artifact_paths(job_id)` làm policy typed duy nhất qua
  `PdfLayoutArtifactPaths`.
- `save_uploaded_pdf()` cũng dùng policy typed này, nên upload không có đường
  dẫn riêng bị lệch với workflow/layout routes.
- Cập nhật unit/contract tests để khóa boundary và tránh helper quay trở lại.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_pdf_layout_job_store.py tests/test_phase_7_pdf_layout_wrapper.py`
- Full suite: `1028 passed, 18 skipped, 1 warning`.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái còn lại

Live model-service smoke và production parity chưa thể xác minh trong checkout
này vì chưa có endpoint, credential và production catalog được cấp. Đây là
blocker môi trường, không phải kết luận rằng live path đã hoạt động.
