# Iteration 246 — khóa ranh giới dependency legacy của Phase 7

## Mục tiêu

Bổ sung enforcement test cho yêu cầu Phase 7: package `saxophone` không được
vô tình kéo lại UI/runtime legacy (`pdf_layout_web`, `extracted`, `music_rag`)
vào các module mới. Compatibility adapter hiện hữu cho legacy retrieval vẫn
được giữ đúng phạm vi migration.

## Thay đổi

- Bổ sung `test_backend_package_does_not_import_legacy_runtime_modules` trong
  `tests/test_phase_7_dependency_enforcement.py`.
- Test quét import ở toàn bộ `src/saxophone`; chỉ cho phép
  `saxophone/retrieval/adapters.py` import `music_rag` vì đây là adapter parity
  legacy đã được ghi trong Phase 5.
- Không cho phép các package mới import `pdf_layout_web` hoặc `extracted`, và
  không cho phép module mới khác import `music_rag`.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **7 passed**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Ghi chú phát hiện

Lần chạy test đầu tiên đã phát hiện `saxophone/retrieval/adapters.py` còn dùng
`music_rag.semantic` để duy trì legacy compatibility. Vì kế hoạch refactor
cho phép giữ adapter này cho tới khi có parity đầy đủ, enforcement được thiết
kế theo allowlist hẹp thay vì xóa dependency một cách suy đoán.

Live model-service smoke và production golden parity vẫn chưa thể xác minh
trong checkout này vì thiếu endpoint, credential và production catalog thật.
