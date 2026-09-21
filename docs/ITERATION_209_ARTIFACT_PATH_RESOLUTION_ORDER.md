# Iteration 209 - thu tu kiem tra symlink cua artifact path

## Pham vi

Tiep tuc harden `LocalArtifactRepository` theo yeu cau safe-path va fail-closed
trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.

## Thay doi

- `_path_for()` kiem tra tung component cua artifact path bang `is_symlink()`
  truoc khi goi `Path.resolve()`.
- Neu component la symbolic link, repository dung ngay voi
  `FileExistsError`, khong dereference duong dan khong tin cay truoc.
- Them regression test bao dam `resolve()` khong duoc goi truoc khi symlink
  guard chay.

## Bang chung kiem thu

- `uv run pytest tests/test_phase_2_artifact_storage_contract.py --basetemp=.pytest-tmp -q`
  -> **31 passed, 1 skipped**.
- `python -m compileall -q src tests` -> dat.
- `git diff --check` -> dat.

Live model-service smoke va production golden parity van chua the xac minh vi
checkout thieu endpoint, credential va production catalog that.
