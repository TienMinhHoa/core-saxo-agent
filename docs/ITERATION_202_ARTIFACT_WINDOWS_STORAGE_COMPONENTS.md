# Iteration 202 — Artifact identity an toàn khi lưu trên Windows

## Phạm vi

`ArtifactRef.artifact_id` và `ArtifactRef.version` là identity logic, nhưng
`LocalArtifactRepository` ánh xạ chúng thành path trên filesystem. Vì vậy mọi
segment của hai field này phải portable trên Windows, không chỉ chống traversal.

## Thay đổi

- Mở rộng `is_safe_artifact_reference` để từ chối segment kết thúc bằng dấu
  chấm/khoảng trắng hoặc chứa ký tự Windows không hợp lệ (`< > " | ? *`).
- Từ chối Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
  `LPT1`–`LPT9`), kể cả dạng có extension.
- Áp dụng chung cho từng segment của cả `artifact_id` và `version`, giữ nguyên
  contract NFC, traversal và separator hiện có.

## Bằng chứng

- TDD trước implementation: targeted test ghi nhận **7 failure** đúng với các
  identity Windows không an toàn.
- Sau implementation: `uv run pytest tests/test_phase_2_artifact_reference_contract.py tests/test_phase_2_artifact_storage_contract.py tests/test_phase_7_api_routes.py -q --basetemp=.pytest-tmp-202`
  đạt **128 passed, 1 skipped, 1 warning**.
- Skip duy nhất là symbolic-link test vì Windows checkout không có quyền tạo
  symbolic link (`WinError 1314`), không liên quan thay đổi iteration này.

## Còn lại

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
