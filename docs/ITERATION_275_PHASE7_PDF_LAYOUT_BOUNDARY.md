# Iteration 275 — ranh giới compatibility cho PDF layout

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: file
`src/pdf_layout_web.py` không còn giữ business logic/orchestration của backend.
Giữ nguyên lệnh `pdf-layout-web` và khả năng import `pdf_layout_web.app` để
không phá compatibility trong giai đoạn strangler migration.

## Thay đổi

- Chuyển implementation FastAPI PDF layout vào
  `src/saxophone/interfaces/pdf_layout_web.py`.
- Thu gọn `src/pdf_layout_web.py` thành wrapper chỉ export `app` và `main`.
- Giữ project root resolution đúng sau khi di chuyển module.
- Đặt import OCR legacy `extracted.parse_pdf_2_md` sau runtime compatibility
  boundary; backend package không có static import tới legacy/model runtime.
- Thêm contract test chứng minh wrapper không còn tạo FastAPI app, route hoặc
  extraction orchestration trực tiếp.

## Bằng chứng kiểm chứng

- TDD targeted: `uv run pytest tests/test_phase_7_pdf_layout_wrapper.py tests/test_phase_7_backend_entrypoint.py -q` → **3 passed**.
- Offline full suite: `uv run pytest -q` → **961 passed, 18 skipped, 1 warning**.
- Các test skip là do Gradio/sample source hoặc quyền tạo symbolic link trên
  Windows; không phải lỗi migration.
- `uv run python -m compileall -q src tests` và `git diff --check` đều đạt.
- Live model-service smoke và production golden parity vẫn chưa xác minh vì
  checkout không có endpoint, credential và production catalog thực tế.

## Trạng thái tiêu chí liên quan

Tiêu chí “không còn business logic trong root `pdf_layout_web.py`” đã đạt ở
mức source boundary offline. PDF layout OCR legacy vẫn là compatibility path,
được lazy-load và chưa được tuyên bố là model-service production parity.
