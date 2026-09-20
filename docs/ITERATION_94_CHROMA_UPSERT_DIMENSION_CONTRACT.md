# Iteration 94 - Contract dimension embedding khi upsert Chroma

## Mục tiêu

Tiếp tục thực hiện yêu cầu trong `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`:
adapter Chroma phải validate embedding dimension trước khi gọi provider.

## Thay đổi

- `ChromaVectorIndex.upsert_chunks()` fail-closed nếu một batch chứa các vector
  khác chiều, kể cả khi composition root không truyền `embedding_dimension`.
- Bổ sung regression test chứng minh batch mixed-dimension bị từ chối trước
  provider I/O.

## Bằng chứng kiểm thử

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py -q`.
- Full suite: `uv run pytest -q`.
- Static: `uv run python -m compileall -q src tests` và `git diff --check`.

Các lệnh và số liệu cuối cùng sẽ được cập nhật sau khi chạy validation trong
iteration này.

## Giới hạn

Đây là kiểm chứng offline với fake provider. Live model-service smoke và
production golden parity vẫn cần endpoint, credential và catalog production
thật.
## Kết quả validation

- Targeted `uv run pytest tests/test_phase_4_ingestion_contract.py -q`: **82 passed**.
- Full `uv run pytest -q`: **482 passed, 2 skipped, 1 warning**.
- `uv run python -m compileall -q src tests`: thành công.
- `git diff --check`: không có lỗi whitespace; Git chỉ cảnh báo chuyển LF/CRLF trên Windows.
