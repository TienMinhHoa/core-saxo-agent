# Iteration 289 — đối soát nghiệm thu Phase 7

## Phạm vi

Iteration này đối soát lại các tiêu chí cleanup và dependency enforcement sau
slice retrieval legacy ở Iteration 288. Không phát hiện violation mới đủ nhỏ và
an toàn để tiếp tục sửa code; vì vậy thay đổi của iteration là chốt bằng chứng
nghiệm thu hiện tại, tránh refactor suy đoán.

## Kết quả đối soát

- Backend có một entrypoint ASGI chính `saxophone-api` tại
  `saxophone.main:main`.
- `app.py` và wrapper `pdf_layout_web.py` không còn business/orchestration
  logic; các phần tương thích còn lại trỏ vào facade hoặc namespace backend.
- Dependency guard tiếp tục chặn import provider/GPU trong business contracts,
  chặn HTTP transport ngoài platform/composition root, và giữ legacy import chỉ
  trong `saxophone.retrieval.legacy`.
- Composition root tiếp tục là nơi wiring concrete adapters; các consumer dùng
  public facade tương ứng.

## Bằng chứng kiểm thử

- `uv run pytest -q`: **970 passed, 18 skipped, 1 warning**.
- Các skip chỉ do Gradio, sample source hoặc quyền tạo symbolic link trên
  Windows; không phải lỗi của slice này.
- Cần chạy bổ sung trước khi phát hành: live model-service smoke và production
  golden parity, vì checkout hiện không có endpoint, credential và catalog
  production thật.

## Kết luận

Phase 7 hiện đạt các tiêu chí offline có thể kiểm chứng trong checkout. Trạng
thái production/live vẫn mở và không được đánh dấu hoàn tất chỉ dựa trên test
offline.
