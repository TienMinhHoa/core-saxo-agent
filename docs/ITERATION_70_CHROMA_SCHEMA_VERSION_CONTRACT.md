# Bằng chứng Iteration 70 — contract schema version của Chroma

## Phạm vi

Siết một điểm nhỏ trong Phase 1 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: composition root phải nhận diện collection Chroma có schema version không tương thích trước khi đưa collection vào application adapter.

## Thay đổi

- `create_chroma_vector_index` kiểm tra metadata `schema_version` với version canonical `saxo-chunk-v1`.
- Collection có version khác bị từ chối bằng `ValueError` với thông báo không làm lộ đường dẫn hoặc credential.
- Collection legacy không có field `schema_version` vẫn được chấp nhận để bảo toàn compatibility; đây là trạng thái cần migration riêng, không bị giả định là đã được nâng version.
- Thêm test persistence tạo collection có `legacy-schema` và xác minh bị fail-closed.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_1_chroma_live_contract.py -q --basetemp=.pytest-tmp
3 passed

uv run pytest -q --basetemp=.pytest-tmp
414 passed, 2 skipped, 1 warning
```

Đã kiểm chứng thêm `compileall` và `git diff --check` sau khi hoàn tất thay đổi. Live model-service smoke và production parity vẫn chưa được xác minh vì checkout chưa có endpoint, credential và catalog production.

