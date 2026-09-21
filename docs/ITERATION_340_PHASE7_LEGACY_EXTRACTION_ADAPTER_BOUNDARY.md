# Iteration 340 - tách adapter extraction PDF legacy khỏi workflow

## Phạm vi

Iteration này xử lý một đơn vị nhỏ của Phase 7: workflow không tự biết cách
load provider legacy `extracted.parse_pdf_2_md`. Phần tương thích tạm thời được
đưa vào adapter `saxophone.extraction.legacy`; workflow chỉ giữ state transition
và gọi một boundary đã đặt tên.

Đây là bước trung gian, chưa tuyên bố đã thay local OCR bằng model service
remote. Provider legacy vẫn được giữ để bảo toàn hành vi hiện tại và sẽ là ứng
viên thay thế sau khi có artifact-transfer contract/live endpoint phù hợp.

## Thay đổi

- Thêm `run_legacy_extraction()` trong `src/saxophone/extraction/legacy.py`.
- `workflows/pdf_layout_extraction.py` không còn import `importlib` hoặc biết
  module `extracted.parse_pdf_2_md`.
- Giữ nguyên state transitions, progress callback, cleanup pipeline và xử lý
  lỗi để không đổi hành vi PDF viewer.
- Thêm dependency-enforcement test bảo vệ boundary này.

## Bằng chứng kiểm tra

- `uv run pytest -q tests/test_phase_7_pdf_layout_wrapper.py tests/test_phase_7_dependency_enforcement.py`
  -> **80 passed**.
- `uv run pytest -q` -> **1061 passed, 18 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` -> đạt.
- `git diff --check` -> đạt.

## Trạng thái còn lại

Live model-service smoke và production parity chưa thể chạy vì checkout không
có endpoint, credential và production catalog được phê duyệt. Adapter legacy
vẫn là compatibility path có chủ đích, không phải bằng chứng remote extraction
đã hoạt động.
