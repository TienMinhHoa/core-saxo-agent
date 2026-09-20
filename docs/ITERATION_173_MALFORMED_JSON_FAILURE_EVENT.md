# Iteration 173 - failure event cho JSON response khong hop le

## Pham vi

Bo sung contract regression cho `LiteLLMModelClient`: HTTP 200 nhung body khong
phai JSON hop le phai bi map thanh `ModelValidationError` va dong thoi phat
structured failure event an toan.

## Ket qua

- Test moi xac nhan event co ten `model.request.failed`, `reason_code` la
  `ModelValidationError`, va `output_count` bang 0.
- Test xac nhan event khong lam lo body response (`not-json`) hay truong
  payload nhay cam.
- Khong thay doi fallback hay tu dong chap nhan response loi; boundary typed
  contract van fail-closed theo Solution Architecture Refactor Plan.

## Bang chung kiem tra

- Targeted model-client tests: `57 passed` trong `test_phase_1_litellm_client.py`.
- Full suite: `738 passed, 3 skipped, 1 warning` voi `uv run pytest`.
- Static: `uv run python -m compileall -q src tests` va `git diff --check` deu dat.

Live model-service smoke va production golden parity van chua duoc xac minh
vi checkout khong co endpoint, credential va production catalog that.
