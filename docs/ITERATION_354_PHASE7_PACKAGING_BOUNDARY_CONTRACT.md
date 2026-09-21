# Iteration 354 — hợp đồng packaging không tái đưa OCR legacy vào backend

## Phạm vi

Iteration này củng cố một lát cắt nhỏ của Phase 7 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: backend target không được quảng
bá package `extracted*`, vì package đó chứa provider OCR/Paddle chạy local và
đã nằm ngoài dependency/runtime boundary của backend.

Compatibility adapter vẫn được giữ trong source tree cho đến khi có parity và
quyết định migration riêng. Việc giữ source compatibility không đồng nghĩa
với việc đóng gói nó vào wheel backend.

## Thay đổi

- Contract test đọc metadata TOML bằng `tomllib`, thay vì dò đúng một chuỗi
  formatting trong `pyproject.toml`.
- Test yêu cầu chính xác hai pattern package được phép là `music_rag*` và
  `saxophone*`, đồng thời fail nếu bất kỳ pattern nào bắt đầu bằng
  `extracted` xuất hiện lại.

## Bằng chứng xác minh

- Targeted Phase 7 dependency contract: chạy lại sau thay đổi và phải xanh.
- Full offline suite: chạy lại sau thay đổi và phải xanh.
- `compileall`: kiểm tra cú pháp Python.
- `git diff --check`: kiểm tra whitespace.
- Live model-service smoke/production parity: chưa xác minh vì checkout hiện
  không có endpoint, credential và production catalog thật.

## Kết luận

Lát cắt packaging enforcement đã được làm bền hơn trước metadata drift; không
thay đổi behavior runtime hay xóa compatibility adapter khi chưa có golden
parity production.
