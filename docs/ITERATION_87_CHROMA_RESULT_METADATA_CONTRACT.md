# Iteration 87 — Hợp đồng metadata kết quả Chroma

## Phạm vi

Siết validation ở chiều đọc của `ChromaVectorIndex.search`. Provider không được
đưa metadata có key rỗng, số không hữu hạn hoặc list lồng nhau vào `VectorHit`.

## Thay đổi

- Bổ sung validator cho từng metadata mapping trong kết quả Chroma.
- Từ chối kết quả sai trước khi tạo `VectorHit`; không có dữ liệu sai lọt vào
  retrieval boundary.
- Bổ sung regression cases cho `NaN`, list lồng nhau và key chỉ chứa khoảng trắng.

## Bằng chứng

- Targeted: `uv run pytest tests/test_phase_4_ingestion_contract.py` — `75 passed`.
- Full suite: `uv run pytest` — `461 passed, 2 skipped, 1 warning`.
- Static: `uv run python -m compileall -q src tests` và `git diff --check` — đạt.

## Trạng thái

Offline contract đã được khóa. Live model-service và production parity vẫn chưa
thể xác minh vì checkout hiện không có endpoint, credential và catalog production.
