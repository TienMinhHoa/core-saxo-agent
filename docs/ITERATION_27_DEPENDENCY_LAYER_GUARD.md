# Iteration 27 — Guard dependency layer theo kiến trúc

## Phạm vi

Theo mục 24 và tiêu chí nghiệm thu 2–4 của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`, iteration này khóa import graph ở
mức AST. Đây là lát cắt enforcement nhỏ, không đổi runtime production code.

## Thay đổi

- Bổ sung `_saxophone_imports` để đọc chính xác các import nội bộ, tách khỏi
  guard SDK/GPU hiện có.
- Bắt buộc các business package (`documents`, `extraction`, `ingestion`,
  `retrieval`, `chat`, `tagging`, `workflows`) không phụ thuộc vào
  `interfaces`, `app` hoặc `main`.
- Giữ ranh giới retrieval/chat: retrieval không gọi chat; chat chỉ dùng
  contract retrieval, không gọi adapter retrieval cụ thể; ingestion không gọi
  HTTP interface.

## Bằng chứng

Lệnh kiểm tra:

```text
uv run pytest tests/test_phase_7_dependency_enforcement.py -q
```

Kết quả iteration 27: **6 passed**.

Guard này là kiểm tra source-level offline. Nó không thay thế live model-service
smoke hoặc kiểm chứng deployment production; các blocker đó vẫn được theo dõi
riêng trong `LIVE_MODEL_SERVICE_SMOKE_STATUS.md`.

## Hậu kiểm

Khoảng trống trước đây là test dependency chỉ chặn SDK/GPU và contract job cũ,
chưa phát hiện được business module vô tình import ngược vào HTTP/composition
root. Quy tắc tổng quát: sau mỗi thay đổi package boundary, thêm một AST guard
cho hướng phụ thuộc hợp lệ trước khi mở rộng implementation.
