# Iteration 361 — hợp đồng candidate tag của Phase 8

## Phạm vi

Tiếp tục Phase 8 paragraph tagging theo hướng Clean Code: xác thực dữ liệu
`existing_tags` ngay tại DTO `TagConflictResolution`, trước khi tạo tập lookup
cho conflict resolution.

## Thay đổi

- Thêm regression test cho ba đầu vào không hợp lệ: tag rỗng, tag trùng và
  phần tử không phải chuỗi.
- Validator hiện trả về `ValueError` có thông báo ổn định cho các trường hợp
  trên, sau đó mới chuẩn hóa chuỗi và kiểm tra candidate được tham chiếu.
- Không thay đổi luồng generation, resolution, persistence hoặc nội dung
  paragraph nguồn.

## Bằng chứng kiểm thử

- Targeted Phase 8: `uv run pytest tests/test_phase_8_conflict_resolution_contract.py tests/test_phase_8_remote_tagging.py tests/test_phase_8_tag_paragraph_use_case.py -q` → **17 passed**.
- Full offline suite: `uv run pytest -q` → **1073 passed, 18 skipped, 1 warning**.
- Các test symbolic-link bị skip vì tài khoản Windows hiện tại không có
  quyền tạo symbolic link; test Gradio bị skip vì dependency không cài trong
  môi trường này.
- Live model-service smoke và production golden parity chưa được xác minh vì
  checkout không có endpoint, credential và production catalog thật.

## Kết luận

Boundary DTO Phase 8 hiện fail-closed cho candidate tag: dữ liệu rỗng, sai
kiểu hoặc trùng không thể đi tiếp vào conflict resolution.
