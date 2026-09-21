# Iteration 232 - bounded I/O cho xoa knowledge sidecar

## Pham vi

Tiep tuc yeu cau async va file-safety trong
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` cho `JsonKnowledgeRepository`.

## Thay doi

- Chuyen ca viec tinh path va `unlink` cua `delete()` vao cung bounded worker.
- Them regression test xac minh `_path_for()` khong chay tren event-loop thread.
- Giu nguyen semantics: chunk khong ton tai van tra `FileNotFoundError`.

## Bang chung kiem thu

- Test truoc khi sua da fail, vi `_path_for()` duoc goi tren caller thread.
- `uv run pytest tests/test_phase_2_json_knowledge_repository.py -q`: **7 passed, 4 skipped**.
- Full suite, `compileall` va `git diff --check` duoc chay sau khi hoan tat.

## Trang thai con lai

Live model-service smoke va production golden parity van chua xac minh trong
checkout nay vi thieu endpoint, credential va production catalog thuc te.
