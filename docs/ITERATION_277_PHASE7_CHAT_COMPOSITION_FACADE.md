# Iteration 277 - composition root dùng facade chat

## Mục tiêu

Hoàn tất một điểm phụ thuộc còn sót trong Phase 7: composition root phải lấy
use case và port chat qua public facade `saxophone.chat`, thay vì biết các
module triển khai bên trong.

## Thay đổi

- `saxophone.app.factory` chuyển `AnswerQuestion`, `AnswerGenerator` và
  `ImageArtifactGate` sang import từ `saxophone.chat`.
- Thêm contract test AST để ngăn factory quay lại import trực tiếp
  `chat.service`, `chat.ports`, `chat.models` hoặc `chat.remote_answer`.

## Bằng chứng kiểm tra

- Targeted dependency suite: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q` → **36 passed**.
- Sẽ chạy full suite, `compileall` và `git diff --check` trước khi kết thúc iteration.

Live model-service smoke và production golden parity vẫn chưa xác minh vì
checkout chưa có endpoint, credential và catalog production thực tế.
