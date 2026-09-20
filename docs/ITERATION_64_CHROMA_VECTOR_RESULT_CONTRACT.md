# Iteration 64 — hợp đồng result của Chroma VectorIndex

## Phạm vi

Khóa fail-closed tại `saxophone.ingestion.adapters.ChromaVectorIndex` khi
Chroma trả kết quả search sai shape hoặc sai kiểu. Đây là lát cắt tiếp theo
sau việc khóa `documents` và `metadatas` của retrieval adapter ở iteration 63.

## Thay đổi

- Bắt buộc `ids`, `documents`, `metadatas`, `distances` là một nested list duy
  nhất và có cùng chiều dài.
- Từ chối id rỗng/sai kiểu, document không phải chuỗi, metadata không phải
  mapping và distance không hữu hạn.
- Chỉ tạo `VectorHit` sau khi toàn bộ provider rows đã qua validation; không
  còn fallback âm thầm sang list rỗng hoặc giá trị mặc định.
- Bổ sung 5 regression cases malformed result trong
  `tests/test_phase_4_ingestion_contract.py`.

## Bằng chứng kiểm thử

- `uv run pytest tests/test_phase_4_ingestion_contract.py -q`: **22 passed**.
- Full suite, `compileall` và `git diff --check` được chạy sau khi hoàn tất
  lát cắt; kết quả được ghi ở phần bàn giao của iteration này.
- Live model-service smoke và production golden parity vẫn chưa thể xác minh
  vì checkout chưa có endpoint, credential và catalog production thật.

## Nguyên tắc rút ra

Provider adapter phải xác thực shape/type trước khi map sang DTO domain. Không
được để constructor DTO là lớp duy nhất phát hiện lỗi, vì khi đó lỗi provider
không có ngữ cảnh và các field thiếu có thể bị fallback âm thầm.
