# Phase 4 - Guard cho tagging workflow

## Mục tiêu

Đảm bảo workflow ingestion không âm thầm bỏ qua yêu cầu tagging. Khi request
chọn profile khác `none-v1`, workflow phải có `IngestDocument` để chạy tagging,
persistence, embedding và indexing theo pipeline đã compose.

## Thay đổi

- `IngestExtractedDocument` ném `ValueError` với thông báo rõ ràng nếu nhận
  `tagging_profile` khác `none-v1` nhưng không có tagging workflow.
- Nhánh tương thích chỉ còn được dùng khi profile là `none-v1`; không có
  fallback im lặng làm mất yêu cầu metadata.
- Bổ sung contract test cho trường hợp cấu hình thiếu workflow.

## Bằng chứng kiểm thử

- `uv run pytest -q tests/test_phase_4_ingest_extracted_document.py` -> **4 passed**.
- Test mới chứng minh profile `tags-v1` bị từ chối khi chỉ compose
  `IndexDocument`.

## Ranh giới còn lại

Kiểm thử hiện là offline với fake artifact/index/provider; chưa xác minh live
model service hoặc Chroma production.
