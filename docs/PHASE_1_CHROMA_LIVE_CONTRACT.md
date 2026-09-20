# Phase 1 - Contract smoke test Chroma persistent

## Phạm vi lát cắt

Lát cắt này kiểm tra bằng Chroma thật (không mock) đường đi tối thiểu của
composition production: `AppSettings` → `PersistentClient` → collection có
metadata dimension/schema → `ChromaVectorIndex` → upsert/list/search/delete.

## Thay đổi

- Thêm test `tests/test_phase_1_chroma_live_contract.py` với collection tạm,
  embedding 3 chiều và dữ liệu tối thiểu.
- Test xác nhận adapter async không gọi SDK Chroma trực tiếp trên event loop,
  metadata document được round-trip, và xóa chunk theo ID hoạt động.
- Cuối test giải phóng object graph của adapter trước khi pytest dọn thư mục.
  Đây là điểm cần thiết trên Windows vì Chroma 1.5.x giữ lock `chroma.sqlite3`
  qua client/collection.

## Bằng chứng kiểm thử

```text
uv run pytest -q tests/test_phase_1_chroma_live_contract.py --basetemp=.pytest-tmp
1 passed

python -m compileall -q src tests
pass

git diff --check
pass
```

## Giới hạn

Smoke test này xác minh persistence local và adapter contract, chưa xác minh
model service/LiteLLM hoặc dữ liệu Chroma production bên ngoài máy test.
