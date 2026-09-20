# Phase 4 — IngestDocument workflow

## Phạm vi

Iteration này chọn hướng Clean Code: bổ sung một coordinator nhỏ cho ingestion,
không kéo logic provider vào workflow. `IngestDocument` nhận các chunk và
paragraph đã chuẩn hóa, gọi `TagAndPersistParagraph` theo thứ tự đầu vào, sau
đó dùng `build_index_inputs` và `IndexDocument` để embed rồi upsert vector.

Extraction, Markdown parsing và HTTP route chưa bị gộp vào lát cắt này.

## Bằng chứng

- Paragraph ngoài tập chunk bị từ chối trước khi gọi tagger.
- Tagging profile và resolution profile được truyền nguyên vẹn.
- Source text không đổi khi tạo index input; tag chỉ đi vào metadata.
- Report chỉ báo `indexed=True` sau khi embedding và upsert hoàn tất.

## Kiểm chứng

Đã chạy test contract mới và toàn bộ test suite offline. Kết quả được ghi trong
log iteration của GNHF; chưa chạy live model service hoặc Chroma thật.
