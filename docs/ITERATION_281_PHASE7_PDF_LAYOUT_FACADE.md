# Iteration 281 - facade extraction cho compatibility route PDF layout

## Phạm vi

Phase 7 yêu cầu inbound adapter và compatibility route phụ thuộc vào public
application contract, không nối trực tiếp vào module triển khai. Sau iteration
280, `interfaces/api.py` đã được guard, nhưng route PDF layout vẫn import trực
tiếp `saxophone.extraction.layout`.

## Thay đổi

- Chuyển import của route `saxophone.interfaces.pdf_layout_web` sang facade
  `saxophone.extraction`.
- Thêm AST contract test để ngăn route quay lại import implementation module.
- Không thay đổi logic normalize block, coordinate-space policy hoặc hành vi
  compatibility của route.

## Bằng chứng kiểm tra

- Targeted dependency tests: `uv run pytest tests/test_phase_7_dependency_enforcement.py -q`.
- Full offline suite: `uv run pytest -q`.
- Kiểm tra cú pháp: `python -m compileall -q src tests`.
- Kiểm tra whitespace: `git diff --check`.
- Live model-service smoke và production golden parity chưa thể xác minh vì
  checkout thiếu endpoint, credential và production catalog thật.
