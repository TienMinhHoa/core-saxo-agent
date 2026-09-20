# Iteration 115 — publish artifact immutable không ghi đè

## Phạm vi

Tiếp tục yêu cầu Artifact storage trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
artifact đã commit theo identity phải immutable, kể cả khi một writer khác tạo file đích sau bước kiểm tra tồn tại.

## Thay đổi

- `LocalArtifactRepository._write_atomically` ghi và `fsync` temporary file như trước.
- Publish dùng hard-link từ temporary file sang destination thay vì `os.replace`.
- Nếu destination xuất hiện cạnh tranh, hard-link thất bại với `FileExistsError`; repository không ghi đè bytes của writer kia.
- Temporary file được dọn cả khi publish thành công và khi publish thất bại.

## Bằng chứng kiểm thử

- Test mới mô phỏng destination được tạo giữa existence-check và commit; bytes cạnh tranh vẫn giữ nguyên và không còn `*.tmp`.
- `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q`: **14 passed**.
- `uv run pytest -q`: **528 passed, 2 skipped, 1 warning**.
- `python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái còn lại

Iteration này chỉ củng cố storage boundary offline. Live model-service smoke và production golden parity vẫn chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production thật.
