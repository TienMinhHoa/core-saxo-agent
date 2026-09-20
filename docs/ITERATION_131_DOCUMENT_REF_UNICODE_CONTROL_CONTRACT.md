# Iteration 131 — contract Unicode và control character của `document_ref`

## Phạm vi

Tiếp tục tiêu chí file safety trong `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
`document_ref` được dùng làm một path component ở artifact/index boundary, nên
policy phải từ chối dữ liệu có thể gây khác biệt biểu diễn hoặc tạo log/path khó
kiểm soát.

## Thay đổi

- `is_safe_document_reference` từ chối mọi control character ASCII (`U+0000`
  đến `U+001F` và `U+007F`).
- Policy từ chối chuỗi Unicode không ở dạng NFC, tương tự contract identity của
  `ArtifactRef`.
- Bổ sung regression tests cho newline, tab, DEL, decomposed Unicode và một
  document reference Unicode NFC hợp lệ.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_2_artifact_reference_contract.py -q`
  — **67 passed**.
- Full offline suite: `uv run pytest -q` — **573 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` — đạt.
- `git diff --check` — đạt; chỉ còn cảnh báo chuyển LF sang CRLF tự nhiên của
  Git trên Windows.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật. Một test
symbolic-link tiếp tục skip trên Windows khi môi trường không có quyền tạo
symlink.
