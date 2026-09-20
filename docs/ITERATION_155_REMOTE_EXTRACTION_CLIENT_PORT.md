# Iteration 155 — Fail-fast model client port cho extraction

## Mục tiêu

Siết boundary của `RemotePdfExtractor` theo SOLUTION_ARCHITECTURE_REFACTOR_PLAN:
adapter phải nhận một model-service port hợp lệ, không để lỗi thiếu `invoke` chỉ
xảy ra sau khi request đã bắt đầu.

## Thay đổi

- Constructor kiểm tra `model_client.invoke` là callable.
- Nếu port sai, adapter ném `ValueError` ngay khi composition root khởi tạo.
- Thứ tự guard giữ nguyên ưu tiên lỗi cấu hình `model` và `response_schema`.
- Bổ sung regression test cho client không có callable `invoke`.

## Bằng chứng kiểm chứng

- `uv run pytest tests/test_phase_3_remote_pdf_extractor.py --basetemp=.pytest-tmp-155 -q`: **22 passed**.
- `uv run pytest --basetemp=.pytest-tmp-155 -q`: **672 passed, 3 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: đạt.
- `git diff --check`: đạt.

## Trạng thái còn lại

Live model-service smoke và production golden parity chưa thể chạy vì checkout
chưa có endpoint, credential và catalog production thật. Đây là blocker môi
trường, không phải kết luận rằng provider production đã đạt.
