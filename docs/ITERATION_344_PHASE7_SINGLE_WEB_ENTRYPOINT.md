# Iteration 344 - Chỉ quảng bá một web entrypoint

## Phạm vi

Phase 7 yêu cầu backend có một web entrypoint và composition root rõ ràng.
Checkout vẫn giữ `src/pdf_layout_web.py` để tương thích import/module cũ, nhưng
metadata đóng gói không nên quảng bá module tương thích đó như một web CLI thứ
hai.

## Thay đổi

- Xóa script `pdf-layout-web` khỏi `[project.scripts]` trong `pyproject.toml`.
- Giữ nguyên module tương thích `src/pdf_layout_web.py` và các contract test của
  legacy UI; thay đổi này không xóa code runtime ngoài phạm vi packaging metadata.
- Thêm test dependency-enforcement bảo đảm script legacy không quay lại.

## Bằng chứng

- TDD red trước thay đổi: test mới fail vì metadata còn chứa
  `pdf-layout-web = "pdf_layout_web:main"`.
- TDD green sau thay đổi: `uv run pytest tests/test_phase_7_dependency_enforcement.py tests/test_phase_7_pdf_layout_wrapper.py -q --basetemp=.pytest-tmp-344`
  đạt **82 passed**.
- `saxophone-api = "saxophone.main:main"` vẫn là web backend entrypoint duy
  nhất; `music-rag` vẫn là CLI compatibility, không phải ASGI entrypoint.
- Full suite: `uv run pytest -q --basetemp=.pytest-tmp-344-rerun` đạt **1063
  passed, 18 skipped, 1 warning**. Lần chạy đầu bị chạy chồng và tạo SQLite
  lock trong thư mục tạm; lần chạy lại tuần tự đã xanh.
- Live model-service smoke và production parity chưa xác minh vì checkout không
  có endpoint, credential và production catalog thật.
