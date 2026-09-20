# Phase 3 - Chuẩn hóa artifact output từ model service

## Mục tiêu

Đảm bảo output `markdown`, `layout` và `manifest` của model service có thể đi
qua transport JSON mà vẫn trở thành `ArtifactRef` bất biến, có metadata đủ để
repository kiểm tra checksum và kích thước trước khi ghi.

## Thay đổi

- `RemotePdfExtractor` tiếp tục chấp nhận `ArtifactRef` đã được tạo sẵn cho
  các fake/in-process adapter.
- Khi output là mapping JSON, adapter chuyển `kind` sang `ArtifactKind` rồi
  khởi tạo `ArtifactRef` để chạy đầy đủ validation identity, media type,
  SHA-256 và `size_bytes`.
- Mapping thiếu field hoặc có metadata sai bị từ chối trước khi tạo
  `PdfExtractionResult`; không có fallback âm thầm sang dữ liệu chưa validate.

## Bằng chứng kiểm thử

- Test mới kiểm tra ba artifact JSON được map thành công và giữ lại media type
  riêng của từng artifact.
- Test mới kiểm tra các lỗi `kind`, `sha256` và `size_bytes`.
- `uv run pytest -q`: **259 passed, 2 skipped, 1 warning**.
- Hai test skip là do dependency Gradio và sample source không có trong
  checkout; không phải regression của lát cắt này.
- `python -m compileall -q src tests` và `git diff --check` đều đạt.

## Ranh giới còn lại

Lát cắt này chỉ chuẩn hóa metadata artifact trong response. Việc tải payload
thực tế từ remote service qua controlled URI/upload và smoke test với model
service thật vẫn cần một contract/adapter riêng; chưa claim upload-to-indexed
end-to-end.
