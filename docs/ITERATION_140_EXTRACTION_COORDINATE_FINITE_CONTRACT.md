# Iteration 140 — contract tọa độ extraction hữu hạn

## Phạm vi

Tiếp tục refactor theo `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, tập trung
vào coordinate contract của extraction. Tọa độ bbox là provenance dùng để map
layout/OCR evidence, nên không được nhận giá trị không hữu hạn.

## Thay đổi

- `ExtractionCoordinate` nay fail-closed nếu bất kỳ thành phần bbox nào là
  `NaN`, `+Inf` hoặc `-Inf`.
- Validator cũng loại boolean và kiểu không phải số trước khi gọi kiểm tra
  hữu hạn; contract không để lỗi kiểu Python rò ra thay cho `ValueError`.
- Bổ sung regression tests cho cả ba dạng giá trị không hữu hạn.

## Bằng chứng kiểm thử

- TDD targeted: `uv run pytest tests/test_phase_3_extraction_contract.py -q
  --basetemp=.pytest-tmp`.
- Full offline suite và `python -m compileall -q src` sẽ được chạy sau thay đổi.
- Live model-service smoke và production golden parity vẫn cần endpoint,
  credential và catalog production thật; checkout hiện chưa có các điều kiện đó.
