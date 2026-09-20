# Iteration 134 — Contract `source_texts` của EvidenceBundle

## Phạm vi

Harden boundary retrieval → chat theo mục 8, 11 và 13 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: mọi key trong `EvidenceBundle.source_texts`
phải là reference canonical trước khi evidence được chuyển tiếp.

## Thay đổi

- `EvidenceBundle` nay kiểm tra key `source_texts` bằng cùng invariant canonical
  (không whitespace đầu/cuối, Unicode NFC) đã áp dụng cho `ChunkHit` và
  `selected_refs`.
- Bổ sung regression tests cho leading whitespace, trailing whitespace và Unicode
  decomposed.

## Bằng chứng kiểm thử

- Trước khi sửa, 3 test mới thất bại vì key sai chỉ bị phát hiện gián tiếp ở bước
  so khớp tập key, chưa có contract validation riêng.
- Sau khi sửa: `uv run pytest tests/test_phase_5_retrieval_contract.py -q` — **36 passed**.
- Kiểm tra bổ sung: `uv run pytest -q` — **588 passed, 3 skipped**.
- `uv run python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt.

## Trạng thái còn lại

Live model-service smoke và production golden parity chưa thể xác minh trong
checkout này vì chưa có endpoint, credential và catalog production được phê duyệt.
