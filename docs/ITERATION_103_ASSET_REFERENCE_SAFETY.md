# Iteration 103 - Khóa reference ảnh tại asset API

## Phạm vi

Kế hoạch kiến trúc yêu cầu asset path phải nằm trong dạng relative an toàn,
chống path traversal và được phục vụ qua asset service đã validate. Iteration
này xử lý một đơn vị nhỏ còn thiếu: route `GET /api/v1/assets/{asset_ref}`
không được chuyển reference có spelling không canonical sang resolver.

## Thay đổi

- Tách policy thuần `documents.policies.is_safe_relative_image_reference`;
- dùng policy tại `SafeImageArtifactGate` và tại API boundary;
- route trả `422 unsafe image reference` và không gọi resolver khi reference có
  backslash, scheme/host, absolute path, `..`, hoặc spelling path không
  canonical.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_api_routes.py tests/test_phase_6_image_artifact_repository_gate.py -q
29 passed, 1 warning
```

Regression test dùng `images%5Cpage.png`, xác nhận route fail-closed trước khi
resolver nhận input (`resolver.calls == []`). Full-suite **496 passed, 2
skipped, 1 warning**, `compileall` và `git diff --check` đều đã chạy thành
công.

## Trạng thái còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
