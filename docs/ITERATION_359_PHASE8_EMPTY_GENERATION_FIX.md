# Iteration 359 — Khóa invariant resolution của Phase 8

## Phạm vi

Tiếp tục slice Phase 8 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Mục tiêu nhỏ của iteration này là bảo đảm output conflict resolution không thể chứa resolution mồ côi khi model không sinh tag nào.

## Thay đổi

- Cập nhật `TagConflictResolution.__post_init__` để luôn kiểm tra tập `generated_tags` và tập `resolutions` phải khớp chính xác.
- Trường hợp `generated_tags=()` nhưng có resolution nay bị từ chối với lỗi contract `each generated tag must have exactly one resolution`.
- Giữ kiểm tra candidate trước invariant mapping để bảo toàn contract lỗi hiện hữu cho `reuse_existing` và danh sách candidate rỗng.

## Bằng chứng kiểm thử

- Targeted Phase 8: `uv run pytest tests/test_phase_8_conflict_resolution_contract.py tests/test_phase_8_remote_tagging.py tests/test_phase_8_tag_paragraph_use_case.py -q` → **12 passed**.
- Full suite: `uv run pytest -q` → **1068 passed, 18 skipped, 1 warning**.
- Các skip là giới hạn môi trường đã biết: Gradio chưa cài, symbolic link Windows bị hạn chế, và sample source không có.
- Live model-service smoke và production parity chưa thể chạy vì checkout vẫn không có endpoint, credential và catalog production thật.

## Kết luận

Slice invariant empty-generation của Phase 8 đã hoàn tất ở mức offline/domain contract. Stop condition toàn bộ tài liệu chưa đạt vì live model-service smoke và production parity vẫn bị block bởi hạ tầng ngoài checkout.
