# Iteration 348 - chuẩn hóa backend chính trong README

## Phạm vi

Đối chiếu exit criteria Phase 7 trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md` với phần mở đầu `README.md`.

## Thay đổi

- README hiện nêu ngay từ phần mở đầu rằng `saxophone-api` là backend web chính.
- Gradio và `app.py` được mô tả đúng là compatibility UI legacy, không thuộc
  runtime backend mặc định.
- Thêm contract test để ngăn README quay lại mô tả Gradio như ứng dụng chính.

## Bằng chứng

- Contract Phase 7 chạy xanh cùng các test entrypoint/dependency.
- `python -m compileall -q src tests` chạy thành công.
- `git diff --check` chạy thành công.

Phạm vi này chỉ đồng bộ runbook và guard tài liệu; không xóa compatibility UI vì
quyết định retire legacy path vẫn cần feature parity và migration decision riêng.
Live model-service smoke/production parity vẫn chưa thể xác minh vì checkout không
có endpoint, credential và production catalog thật.
