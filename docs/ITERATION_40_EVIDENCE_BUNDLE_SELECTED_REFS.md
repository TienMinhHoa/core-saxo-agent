# Iteration 40 — khóa selected refs của EvidenceBundle

## Mục tiêu

Tiếp tục Phase 5 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` bằng một lát cắt
nhỏ: evidence đi từ retrieval sang chat không được chứa `selected_refs` trỏ
đến chunk không có trong kết quả retrieval hoặc không có source text tương ứng.

## Thay đổi

- `EvidenceBundle` kiểm tra `selected_refs` là duy nhất.
- Mỗi selected ref phải tồn tại trong `ChunkHit` của bundle.
- Mỗi selected ref phải có source text đã được validate trong `source_texts`.
- Bổ sung contract test cho hai trường hợp vi phạm trên.

Các kiểm tra này chỉ củng cố DTO boundary; không thay đổi adapter retrieval,
chat use case hoặc fallback provider.

## Bằng chứng kiểm thử

- TDD targeted: trước implementation, test mới fail vì bundle chấp nhận ref
  không hợp lệ (`1 failed, 6 passed`).
- Sau implementation: `uv run pytest tests/test_phase_5_retrieval_contract.py
  tests/test_retrieve_evidence.py -q` → **11 passed**.
- Full suite: `uv run pytest -q` → **337 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` → đạt.
- `git diff --check` → đạt; chỉ còn cảnh báo chuyển đổi line ending CRLF của
  Git trên Windows.

## Trạng thái nghiệm thu

Đã đóng thêm một contract offline cho tiêu chí evidence được validate trước
khi chat sử dụng. Live model-service smoke và golden parity production vẫn
chưa thể xác minh vì checkout chưa có endpoint, credential và catalog production
được phê duyệt; stop condition toàn bộ của kế hoạch chưa đạt.
