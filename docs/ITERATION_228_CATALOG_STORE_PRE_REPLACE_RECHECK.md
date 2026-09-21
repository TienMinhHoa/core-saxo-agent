# Iteration 228 — Re-check path trước khi replace CatalogStore

## Phạm vi

Theo mục **20. Security và file safety** trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, `CatalogStore` phải fail-closed
khi đường dẫn persistence bị thay đổi trong lúc ghi atomic.

## Thay đổi

- `CatalogStore.save()` re-check root và `catalog.json` sau khi đóng temporary
  file, ngay trước `os.replace()`.
- Nếu lần kiểm tra cuối thất bại, temporary file được dọn qua nhánh cleanup và
  thao tác replace không được gọi.
- Bổ sung regression test TDD mô phỏng path race tại đúng boundary này.

## Bằng chứng

- Red trước implementation: test mới thất bại vì `os.replace()` vẫn được gọi.
- Green sau implementation: `uv run pytest tests/test_catalog_store_safety.py -q
  --basetemp=.pytest-tmp-228-green` đạt **2 passed, 2 skipped**; hai test skip
  là do Windows checkout không có quyền tạo symbolic link (WinError 1314).
- Full offline suite, `compileall` và `git diff --check` được chạy sau thay đổi;
  kết quả được ghi ở handoff của iteration.

## Ngoài phạm vi

Không thay đổi schema catalog, importer/search behavior, hay backend storage.
