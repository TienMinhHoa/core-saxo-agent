# Iteration 55 — canonical identity của EvidenceBundle

## Phạm vi

Iteration này xử lý một slice nhỏ tại boundary retrieval → chat theo
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: `EvidenceBundle` phải tự bảo vệ
identity của query/version và không được nhận các hit thuộc retrieval version
khác.

## Thay đổi

- `EvidenceBundle.query` và `EvidenceBundle.retrieval_version` nay yêu cầu
  chuỗi non-blank, không có khoảng trắng đầu/cuối và ở Unicode NFC canonical.
- `EvidenceBundle` từ chối khi `retrieval_version` của bundle không khớp với
  bất kỳ `ChunkHit` nào trong `hits`.
- Bổ sung test TDD cho 6 trường hợp identity không canonical và 1 trường hợp
  version không khớp.

## Bằng chứng kiểm chứng

- Red phase: test mới thất bại đúng 7 trường hợp trước khi sửa implementation.
- Targeted: `uv run pytest tests/test_phase_5_retrieval_contract.py -q` → **25
  passed**.
- Full suite: `uv run pytest -q` → **367 passed, 2 skipped, 1 warning**.
- Static: `python -m compileall -q src tests` và `git diff --check` đều thành
  công.

## Trạng thái và giới hạn

Slice contract offline này đã hoàn tất. Live model-service smoke và production
golden parity vẫn chưa thể kết luận vì checkout chưa có endpoint, credential và
catalog production thật; iteration này không dùng fake HTTP để thay thế.

