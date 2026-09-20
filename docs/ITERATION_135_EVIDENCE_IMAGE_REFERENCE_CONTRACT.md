# Iteration 135 - Contract image reference trong `EvidenceBundle`

## Phạm vi

Tiếp tục harden boundary retrieval -> chat theo tiêu chí 8, 11, 13 và 21
của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. `EvidenceBundle` phải chặn
image reference không an toàn trước khi evidence được chuyển cho chat hoặc
artifact gate.

## Thay đổi

- `EvidenceBundle.image_refs` tái sử dụng policy chung
  `is_safe_relative_image_reference`.
- Từ chối fail-closed path traversal, absolute path, URL, Windows path và
  control character; vẫn chấp nhận reference tương đối như
  `images/page-1.png`.
- Bổ sung regression cases để chứng minh validation nằm ngay tại evidence
  boundary, không chỉ phụ thuộc vào HTTP route hoặc artifact gate.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_5_retrieval_contract.py tests/test_retrieve_evidence.py -q`
  — **52 passed**.
- `uv run pytest -q` — **593 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt.

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh
trong checkout này vì thiếu endpoint, credential và catalog production được
phê duyệt.
