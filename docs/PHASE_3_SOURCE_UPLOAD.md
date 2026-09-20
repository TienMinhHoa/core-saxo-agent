# Phase 3 - Upload source PDF vào artifact repository

## Phạm vi iteration 29

Iteration này hoàn thiện lát cắt nhỏ còn thiếu trước `ProcessDocument`: API có
thể nhận một file PDF, tạo `ArtifactRef` typed và persist payload qua
`ArtifactRepository`. Route không biết filesystem; composition root inject
repository như một port.

## Hành vi đã triển khai

- Thêm `POST /api/v1/documents/{document_ref}/source` với multipart field `file`.
- Chỉ nhận `Content-Type: application/pdf`; file khác trả HTTP 415 và không ghi
  repository.
- Artifact được tạo với identity `{document_ref}/source`, version `v1`, kind
  `source_pdf`, size thực tế và SHA-256 tính từ payload.
- Route trả về artifact metadata typed với HTTP 201; bytes được giao cho
  `ArtifactRepository.put`, nên production mặc định dùng
  `LocalArtifactRepository` và test dùng fake port.
- Không thêm job lifecycle, background worker, local path vào API, hay gọi model
  service trong bước upload.

## Bằng chứng kiểm thử

- Red test trước implementation: 2 test upload trả 404 vì route chưa tồn tại.
- Sau implementation:
  `uv run pytest tests/test_phase_7_api_routes.py -q --basetemp=.pytest-tmp`
  đạt **7 passed, 1 warning**.
- Test thành công kiểm tra artifact metadata, SHA-256 có dạng hợp lệ, payload
  được gửi vào repository và lỗi media type không làm phát sinh `put`.

## Ranh giới còn lại

Upload hiện mới tạo source artifact. `ProcessDocument` vẫn là request kế tiếp;
output extraction chưa được persist, ingestion/index chưa được compose và health
vẫn báo ingestion disabled. Live model service/Chroma chưa được smoke test.
