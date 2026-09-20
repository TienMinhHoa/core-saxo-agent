# Phase 7 — Kiểm thử ranh giới dependency

## Phạm vi vòng 66

Chọn phương án Clean Code: biến nguyên tắc dependency inversion thành kiểm thử
offline nhỏ, chạy được trên checkout không có GPU. Vòng này chưa xoá legacy UI
vì `app.py` vẫn là compatibility path và kế hoạch yêu cầu chỉ xoá sau khi có
feature parity cùng quyết định migration.

## Kết quả

- `tests/test_phase_7_dependency_enforcement.py` quét AST, không import module
  thật nên không cần khởi động FastAPI, Chroma hay model service.
- Inbound adapter `saxophone.interfaces.api` không được phụ thuộc trực tiếp vào
  SDK provider (`chromadb`, `openai`, `httpx`, `gradio`, Paddle/PaddleX, Torch).
- Các application use case chính không được import provider SDK; adapter ở
  `saxophone.platform` hoặc module adapter riêng là ranh giới được phép.
- Toàn bộ package `saxophone` được quét AST để chặn import `paddle`, `paddlex`,
  `torch`, `transformers`; backend không kéo local GPU runtime.

## Bằng chứng kiểm chứng

- Targeted: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q` (3 tests)
- Full offline suite: chạy sau khi test mới được thêm; không bao gồm live
  model-service/Chroma smoke.
- Quy tắc này chỉ kiểm tra import tĩnh; chưa chứng minh build image hoặc live
  provider availability.

## Bước tiếp theo

Tiếp tục rà soát dependency/runtime của `app.py` legacy và cập nhật runbook,
nhưng chỉ loại bỏ wrapper sau khi characterization/feature-parity evidence
được ghi nhận.
