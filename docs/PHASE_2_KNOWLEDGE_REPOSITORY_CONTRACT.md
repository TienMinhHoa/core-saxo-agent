# Phase 2 — Hợp đồng knowledge repository

## Phạm vi iteration

Iteration này chọn hướng **Clean Code**: chuẩn hóa một record chunk có kiểu dữ
liệu rõ ràng và port bất đồng bộ cho knowledge repository. Đây là lớp metadata
đầy đủ của knowledge source; nó không lưu bytes của PDF/ảnh và không phụ thuộc
Chroma.

## Thay đổi đã thực hiện

- Thêm `saxophone.documents.knowledge.KnowledgeChunk` dạng immutable.
- Kiểm tra bắt buộc cho identity, `content_hash` SHA-256, khoảng trang, số
  lượng paragraph/image và các danh sách provenance không rỗng.
- Thêm `KnowledgeRepository` với ba thao tác tối thiểu: `upsert`, `get`,
  `delete`.
- Thêm contract tests dùng in-memory fake để chứng minh application code có
  thể test mà không cần filesystem, Chroma hoặc model service.

## Ranh giới dữ liệu

`KnowledgeChunk` giữ `source_ref`, `source_version`, `heading_path`, `tags` và
`image_refs`; artifact repository vẫn giữ bytes bất biến. Vector index về sau
chỉ nhận projection phục vụ tìm kiếm và không trở thành source of truth của
metadata.

## Bằng chứng xác minh

Đã chạy trong môi trường uv của repository:

```text
uv run pytest tests/test_phase_2_knowledge_repository_contract.py -q
4 passed

uv run pytest -q
74 passed, 2 skipped, 1 warning
```

Hai test bị skip là dependency Gradio và sample source chưa có trong checkout,
không liên quan đến thay đổi iteration này. Ruff chưa được cài/expose trong
môi trường hiện tại nên chưa có kết quả lint.

## Giới hạn còn lại

Iteration này chưa thêm adapter JSON/file production và chưa nối record vào
ingestion workflow. Hai việc đó nên thực hiện sau khi contract được giữ ổn
định; vector adapter cũng vẫn là một port riêng.

## Bài học quy trình

Root cause của lần validation hụt đầu tiên là dùng system Python thay vì môi
trường uv của project. Quy tắc tổng quát: trước khi kết luận test không chạy,
kiểm tra toolchain được khai báo bởi repository (`uv run ...`) và ghi rõ phần
kiểm tra nào chưa thực hiện được.
