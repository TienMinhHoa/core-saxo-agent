# Iteration 213 - Đưa validation payload của artifact vào bounded I/O worker

## Phạm vi

Tiếp tục thực hiện yêu cầu async và bounded blocking I/O trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Iteration 212 đã chuyển việc
validate path và đọc file của `get()` sang worker; iteration này xử lý phần
validation kích thước và SHA-256 của `put()`.

## Thay đổi

- `put()` chỉ kiểm tra loại `ArtifactRef` ở application boundary rồi gọi
  `_write_artifact()` qua `anyio.to_thread.run_sync(..., limiter=...)`.
- `_write_artifact()` thực hiện payload validation và atomic write cùng trong
  bounded worker, tránh hashing payload trên event-loop thread.
- Thêm contract test chứng minh `_validate_payload()` chạy ở worker thread.

## Bằng chứng

- Targeted: `35 passed, 1 skipped` với
  `uv run pytest tests/test_phase_2_artifact_storage_contract.py -q
  --basetemp=.pytest-tmp-213`.
- Test symbolic link bị skip trên Windows do môi trường thiếu quyền tạo
  symbolic link (`WinError 1314`); các nhánh fail-closed vẫn có coverage bằng
  monkeypatch.

## Giới hạn xác minh

Iteration này chưa chạy live model-service smoke hoặc production parity vì
checkout vẫn không có endpoint, credential và production catalog được phê
duyệt.
