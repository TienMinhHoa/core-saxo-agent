# Iteration 216 - asset route bắt buộc checksum gate

## Phạm vi

Iteration này xử lý một contract nhỏ trong mục security/file safety của
`SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: API asset không được trả image bytes
chỉ dựa trên `kind` và MIME type. Payload phải đi qua
`RepositoryBackedImageArtifactGate`, để size và SHA-256 của artifact được kiểm
tra trước khi response được tạo.

## Thay đổi

- Composition root tự tạo `RepositoryBackedImageArtifactGate` khi đã có
  `ArtifactRepository` và `ImageArtifactResolver`, đồng thời cho phép test
  inject gate qua `AppOverrides`.
- Asset route yêu cầu gate đã được cấu hình và gọi gate trước khi resolve/read
  payload; nếu repository adapter trả bytes tampered, request bị từ chối với
  HTTP 422 thay vì trả dữ liệu ra browser.
- Bổ sung regression test cho payload sai checksum; test ban đầu đỏ với HTTP
  200 và xanh sau khi nối gate.

## Bằng chứng kiểm thử

- Red trước implementation: `1 failed`, route trả HTTP 200 cho payload sai
  checksum.
- Targeted sau implementation:
  `uv run pytest tests/test_phase_7_api_routes.py -k asset_route -q
  --basetemp=.pytest-tmp-216-green2` -> **7 passed, 1 warning**.
- Full suite, compileall và diff check được ghi nhận ở acceptance status sau
  khi chạy hoàn tất.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout không có endpoint, credential và production catalog thật.
