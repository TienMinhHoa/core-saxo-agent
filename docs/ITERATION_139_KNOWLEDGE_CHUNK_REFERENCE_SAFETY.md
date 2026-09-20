# Iteration 139 — an toàn reference trong `KnowledgeChunk`

## Phạm vi

Tiếp tục thực hiện lựa chọn Clean Code trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, tập trung vào contract của
knowledge repository. Slice này bảo đảm provenance và image reference không bị
nới lỏng khi DTO đi qua repository.

## Thay đổi

- `KnowledgeChunk.source_ref` nay phải là chuỗi canonical: không có khoảng
  trắng đầu/cuối, Unicode phải ở dạng NFC và không chứa ASCII control character.
- Mọi `KnowledgeChunk.image_refs` đều dùng chung policy relative-image
  fail-closed; traversal, absolute path, URL và control character bị từ chối.
- Bổ sung contract tests cho cả nhóm provenance và image reference unsafe.

## Bằng chứng kiểm thử

- TDD targeted: `uv run pytest tests/test_phase_2_knowledge_repository_contract.py
  -q --basetemp=.pytest-tmp` → **11 passed**.
- Full offline suite: `uv run pytest -q --basetemp=.pytest-tmp` → **619 passed,
  3 skipped, 1 warning**.
- `python -m compileall -q src` → đạt.
- `git diff --check` → đạt.

Các test symbolic-link vẫn skip trên Windows vì thiếu quyền tạo symlink; live
model-service smoke và production golden parity vẫn chưa thể xác minh do
checkout chưa có endpoint, credential và catalog production thật.
