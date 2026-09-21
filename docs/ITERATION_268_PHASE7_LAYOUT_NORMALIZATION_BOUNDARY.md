# Iteration 268 — tách chuẩn hóa layout khỏi legacy PDF route

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: giảm business
logic trong `src/pdf_layout_web.py` bằng cách đưa phần chuẩn hóa payload layout
vào package `saxophone.extraction`, nơi có thể kiểm thử độc lập với FastAPI,
subprocess và UI legacy.

## Thay đổi

- Thêm `saxophone.extraction.layout` với:
  - `finite_number`, loại bỏ boolean, giá trị không phải số và số không hữu hạn;
  - `normalize_blocks`, chỉ giữ block hợp lệ và `source_bbox` có kích thước dương;
  - hằng số `RAW_PDF_RASTER_SPACE` ổn định cho contract coordinate space.
- Export các contract trên qua `saxophone.extraction`.
- `pdf_layout_web` giữ wrapper tương thích, nhưng không còn sở hữu logic
  chuẩn hóa block/số.
- Thêm contract tests cho bbox hợp lệ, bbox lỗi, boolean/non-finite values và
  coordinate-space constant.

## Bằng chứng kiểm tra

- `uv run pytest tests/test_extraction_layout_normalization.py tests/test_phase_7_dependency_enforcement.py -q`
  — **33 passed**.
- `uv run pytest -q` — **954 passed, 18 skipped, 1 warning**.
- `python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ có cảnh báo chuyển LF sang CRLF của Git trên
  Windows, không có whitespace error.

Các test skip hiện hữu liên quan Gradio chưa cài, sample source thiếu và quyền
tạo symbolic link trên Windows; không phát sinh từ slice này. Live
model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và production catalog thật.

## Kết luận

Slice này đạt mục tiêu boundary offline và bảo toàn behavior route legacy qua
compatibility wrapper. Stop condition toàn bộ chưa đạt vì live smoke/parity và
một phần migration legacy PDF vẫn cần môi trường hoặc quyết định vận hành bên
ngoài checkout.
