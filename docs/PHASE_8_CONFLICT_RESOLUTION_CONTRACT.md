# Phase 8 - Contract conflict resolution tag

## Kết quả lát cắt

Theo lựa chọn Clean Code, iteration này tách nhiệm vụ resolve conflict thành
boundary riêng sau bước sinh tag. Application chỉ nhìn thấy DTO bất biến và
port async, không phụ thuộc HTTP, SDK hay model/GPU runtime.

Contract hiện có:

- `ExistingTagCandidate` giữ tag tiếng Anh đã tồn tại và ví dụ provenance;
- `TagConflictResolutionRequest` giữ paragraph, generated tags, candidate tags
  và version/profile của task;
- `TagResolution` chỉ cho phép hai action: `reuse_existing` hoặc `keep_new`;
- `TagConflictResolution` yêu cầu mỗi generated tag có đúng một resolution,
  không cho reuse tag ngoài candidate list, và candidate rỗng chỉ được `keep_new`;
- `TagConflictResolver.resolve()` là async provider port độc lập với provider.

Không có fallback im lặng: output không hợp lệ bị từ chối bằng `ValueError` ở
contract boundary. Việc gọi LLM thật, retry, persistence sidecar và wiring vào
ingestion vẫn để ở các lát cắt sau.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_8_conflict_resolution_contract.py -q`: **5 passed**.
- `uv run pytest -q`: **195 passed, 2 skipped, 1 warning**. Hai test skip do
  Gradio/sample source không có trong checkout; không phải regression của lát
  cắt này.
- `uv run python -m compileall -q src`: đạt.
- `git diff --check`: đạt.

## Giới hạn xác minh

Đây là contract/offline verification. Chưa xác minh model service thật, schema
JSON từ provider, retry policy hoặc pipeline paragraph-to-sidecar end-to-end.
