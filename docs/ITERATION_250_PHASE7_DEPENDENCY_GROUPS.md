# Iteration 250 — Tách dependency runtime và dev/test

## Phạm vi

Khóa thêm một invariant của Phase 7 trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
dependency chạy production không được kéo theo công cụ test, trong khi nhóm dev vẫn
phải khai báo rõ công cụ test cần thiết.

## Thay đổi

- Bổ sung test AST/config tại `tests/test_phase_7_dependency_enforcement.py`.
- Test đọc `pyproject.toml` bằng `tomllib` và kiểm tra `pytest` không nằm trong
  `project.dependencies`, có mặt trong `dependency-groups.dev`, đồng thời không bị
  khai báo lại trong `requirements.txt`.
- Allowlist tài liệu này trong `.gitignore` để bằng chứng refactor được theo dõi.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`: **12 passed**.
- Full suite và `compileall` cần được chạy ở bước xác minh cuối iteration.
- Live model-service smoke/production parity vẫn chưa thể xác minh vì checkout không
  có endpoint, credential và catalog production thật.

## Kết luận

Boundary dependency hiện được kiểm tra tự động ở cả hai mặt: loại runtime GPU/local
model và phân tách runtime với dev/test tooling. Đây là enforcement offline; không
thay thế live smoke hoặc deployment verification.
