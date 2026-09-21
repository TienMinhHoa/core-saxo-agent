# Iteration 267 — facade công khai cho workflow

## Mục tiêu

Tiếp tục Phase 7 của `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: composition
root phải dùng API công khai ổn định của module workflow, thay vì biết trực tiếp
các file implementation bên trong.

## Thay đổi

- `src/saxophone/app/factory.py` nay import `IngestExtractedDocument`,
  `ProcessAndPersistDocument` và `ProcessDocument` từ `saxophone.workflows`.
- Bổ sung contract test bảo đảm factory không quay lại import trực tiếp
  `saxophone.workflows.*` implementation.
- Bổ sung contract test xác nhận `saxophone.workflows.__all__` công khai đủ ba
  workflow contract hiện tại.

## Bằng chứng kiểm tra

- Contract Phase 7: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`
  — **30 passed**.
- Full offline suite: `uv run pytest -q` — **951 passed, 18 skipped, 1 warning**.
- Syntax/import compilation: `python -m compileall -q src tests` — đạt.
- Whitespace diff: `git diff --check` — đạt.

Các test skip là kiểm tra phụ thuộc Gradio, sample source hoặc symbolic link bị
giới hạn bởi tài khoản Windows hiện tại; không phải lỗi của thay đổi iteration
này. Live model-service smoke và production golden parity vẫn chưa thể xác minh
trong checkout vì thiếu endpoint, credential và production catalog thật.

## Kết luận

Slice facade workflow đã đạt tiêu chí offline và không thay đổi behavior runtime.
Stop condition toàn cục chưa đạt vì live model-service smoke và production parity
vẫn là blocker môi trường ngoài checkout.
