# Iteration 360 - xác thực profile của hai task tagging

## Phạm vi

Tiếp tục lát cắt Phase 8 theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Mục tiêu
là không cho phép kết quả từ model task được ghi nhận khi profile/version trả về
khác profile mà use case đã yêu cầu.

## Thay đổi

- `TagParagraph` kiểm tra `TagGenerationResult.tagging_profile` khớp
  `tagging_profile` của request trước khi gọi resolver.
- `TagParagraph` kiểm tra `TagConflictResolution.resolution_profile` khớp
  `resolution_profile` của request trước khi tạo `TaggedParagraph`.
- Bổ sung hai regression test cho generation-profile drift và
  resolution-profile drift. Các test dùng candidate hợp lệ để đi tới đúng
  invariant profile.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_8_tag_paragraph_use_case.py -q
5 passed

uv run pytest -q --basetemp=.pytest-tmp-360-full
1070 passed, 18 skipped, 1 warning
```

Các test skip vẫn là giới hạn môi trường đã biết: Gradio chưa cài, symbolic
link không được Windows account cấp quyền, và sample source không có trong
checkout. `compileall` và `git diff --check` cần được chạy ở bước kiểm chứng
cuối iteration.

## Kết luận

Lát cắt validation profile đã hoàn tất ở mức offline/domain contract. Live
model-service smoke và production parity vẫn chưa thể xác minh vì checkout
không có endpoint, credential và production catalog thật.
