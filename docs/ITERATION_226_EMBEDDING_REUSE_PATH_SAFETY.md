# Iteration 226 — an toàn path cho embedding reuse store

## Phạm vi

Iteration này hoàn tất một lát nhỏ của Phase 2 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: adapter
`FileEmbeddingReuseStore` không được ghi hoặc đọc qua path có thể redirect bằng
symbolic link.

## Thay đổi

- Kiểm tra path cache ngay khi khởi tạo; từ chối file hoặc parent component là
  symbolic link.
- Kiểm tra lại path trước khi đọc, sau khi tạo parent directory và trước khi
  tạo lock file, nhằm giảm cửa sổ race khi filesystem bị thay đổi sau
  constructor.
- Thêm contract tests cho symlink file, symlink parent và parent bị thay thế
  sau `mkdir`.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_index_document.py -q --basetemp=.pytest-tmp`
  → **18 passed, 3 skipped**.
- Ba test symlink bị skip có kiểm soát vì Windows runner thiếu quyền tạo
  symbolic link (`WinError 1314`); đây là giới hạn môi trường, không phải test
  failure.
- Full suite, `compileall` và `git diff --check` được chạy sau lát thay đổi.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout không có endpoint, credential và production catalog thật.
