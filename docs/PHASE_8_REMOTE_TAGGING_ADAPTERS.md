# Phase 8 - Adapter tagging paragraph từ model service

## Mục tiêu

Chọn hướng Clean Code: application chỉ biết `TagGenerator` và
`TagConflictResolver`; HTTP/LiteLLM được ẩn sau `ModelClient`. Lát cắt này nối
hai port tagging đã có với external model service mà không đưa SDK/provider vào
use case.

## Thay đổi

- Thêm `RemoteParagraphTagger` cho task `paragraph_tag`, gửi paragraph ID,
  source text, heading/image context và tagging profile.
- Thêm `RemoteTagConflictResolver` cho task `tag_resolve`, gửi generated tags
  cùng candidate tags và chỉ chấp nhận action hợp lệ qua `TagResolution`.
- Cả hai adapter kiểm tra task, response schema, paragraph identity và shape
  của nested output trước khi tạo DTO domain.
- Composition root tạo hai adapter dùng chung `ModelClient`; khi ingestion
  được bật, chúng được ghép vào `TagParagraph` -> `TagAndPersistParagraph` ->
  `IngestDocument`.
- Giữ compatibility path: `tagging_profile=none-v1` tiếp tục index trực tiếp,
  không gọi model tagging. Đây là cần thiết cho các route cũ chưa yêu cầu tag.

## Bằng chứng kiểm thử

- Contract adapter mới: `3 passed`.
- Regression nhóm composition/API/workflow: `20 passed` trước khi chạy toàn bộ.
- Toàn bộ test suite sau khi giữ compatibility path: chạy lại bằng
  `uv run pytest -q`; kết quả được ghi trong handoff iteration.
- `git diff --check` và compileall phải được chạy trước khi kết thúc iteration.

## Ranh giới còn lại

Adapter đã được kiểm tra offline bằng fake `ModelClient`; chưa gọi live model
service nên chưa khẳng định provider thật, prompt/model quality hoặc latency.
Vector index production vẫn cần được cung cấp qua composition override/adapter
phù hợp trước khi claim upload-to-searchable end-to-end.
