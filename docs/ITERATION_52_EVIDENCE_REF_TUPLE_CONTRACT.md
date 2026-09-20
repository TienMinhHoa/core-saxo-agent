# Iteration 52 - khóa kiểu tuple cho refs của EvidenceBundle

## Phạm vi

Khóa một lỗi contract nhỏ tại ranh giới retrieval → chat: `EvidenceBundle`
phải nhận `selected_refs` và `image_refs` dưới dạng tuple bất biến. Nếu nhận
chuỗi, vòng lặp kiểm tra nội dung có thể duyệt từng ký tự và làm DTO vượt qua
validation không đúng ý định.

## Thay đổi

- Bổ sung validation từ chối `selected_refs` hoặc `image_refs` không phải tuple.
- Bổ sung test parametrized cho cả hai trường hợp; test được viết trước và
  chạy đỏ trước khi thêm implementation.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_5_retrieval_contract.py -q`: **9 passed**.
- `uv run pytest -q`: **347 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests` và `git diff --check`: đạt.

## Giới hạn

Đây là kiểm chứng offline của DTO, không phải bằng chứng live model-service,
production catalog parity hoặc deployment. Các blocker đó vẫn được theo dõi
riêng trong `LIVE_MODEL_SERVICE_SMOKE_STATUS.md`.
