# Iteration 266 — sở hữu wiring adapter tại composition root

## Mục tiêu

Khóa thêm tiêu chí Phase 7 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
concrete adapter chỉ được composition root import để lắp ráp; module platform
không được kéo ngược adapter implementation để dùng làm contract.

## Thay đổi

- Bổ sung AST enforcement trong `tests/test_phase_7_dependency_enforcement.py`.
  Guard mới quét toàn bộ `src/saxophone` và chỉ cho phép
  `saxophone.app.factory` import nhóm concrete adapter đã khai báo.
- Giữ ngoại lệ có chủ đích cho `platform/chroma.py`: đây là adapter factory
  duy nhất cần biết implementation `ChromaVectorIndex`; mọi module khác chỉ
  được để `app/factory.py` import nhóm concrete adapter này.

## Bằng chứng kiểm tra

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q` —
  **28 passed**.
- Full suite: `uv run pytest -q` — **949 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` và `git diff --check` — đạt.
- Live model-service smoke
  vẫn chưa xác minh vì checkout không có endpoint, credential và production
  catalog thật.

## Kết luận

Boundary composition root đã được kiểm tra ở cấp source AST cho nhóm concrete
adapter. Đây là enforcement offline; không thay thế production parity hoặc
live smoke.
