# Iteration 240 - cleanup khi khởi tạo ChromaVectorIndex thất bại

## Phạm vi

Tiếp tục harden composition root theo `SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`.
Iteration này chỉ xử lý một failure boundary: `PersistentClient` đã được tạo và
collection đã được validate, nhưng constructor của `ChromaVectorIndex` ném lỗi.

## Thay đổi

- Đưa bước tạo `ChromaVectorIndex` vào cùng `try` với collection/metadata
  validation trong `create_chroma_vector_index`.
- Khi constructor thất bại, factory đóng client Chroma và giữ nguyên exception
  gốc; không để resource bị rò rỉ.
- Thêm regression test TDD mô phỏng constructor thất bại và xác minh client đã
  được đóng.

## Bằng chứng kiểm thử

- Trước khi sửa, test mới thất bại: client vẫn ở trạng thái chưa đóng.
- Sau khi sửa:
  - targeted: `3 passed, 31 deselected` cho các failure cleanup của Chroma;
  - full suite: `924 passed, 18 skipped, 1 warning`;
  - `compileall` và `git diff --check` được chạy cùng bộ kiểm tra kết thúc.

## Giới hạn xác minh

Đây là contract/offline test với fake Chroma client. Live model-service smoke,
production catalog parity và deployment vẫn chưa được xác minh vì checkout chưa
có endpoint, credential và catalog production thật.
