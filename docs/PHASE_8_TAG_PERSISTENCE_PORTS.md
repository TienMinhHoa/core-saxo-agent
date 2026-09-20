# Phase 8 — Port persistence cho tagged paragraph và tag catalog

## Phạm vi lát cắt

Lát cắt này đặt boundary application cho hai dữ liệu metadata mà kế hoạch kiến trúc
yêu cầu giữ ngoài vector index:

- `TaggedParagraphRepository` lưu kết quả tagging có source text nguyên vẹn, keyed bởi
  `paragraph_id` ổn định.
- `TagCatalogRepository` lưu vocabulary tag tiếng Anh dạng string, độc lập với
  paragraph sidecar và có thứ tự trả về deterministic.

Chưa chọn JSON, SQLite hay database cụ thể. Adapter storage là lát cắt tiếp theo;
use case không được import SDK hoặc phụ thuộc Chroma để đáp ứng contract này.

## Bằng chứng kiểm thử

- `tests/test_phase_8_tag_persistence_ports.py`: 3 test contract cho replace/upsert,
  missing record, source preservation, deduplication và deterministic ordering.
- Kiểm thử offline dùng fake in-memory implement port; không gọi LLM, GPU, Chroma hay
  filesystem production.

## Trạng thái

Đã hoàn tất application port contract. Chưa claim Phase 4 exit criteria, vì adapter
persist thật và wiring từ `TagParagraph` vào repository/catalog vẫn còn thiếu.
