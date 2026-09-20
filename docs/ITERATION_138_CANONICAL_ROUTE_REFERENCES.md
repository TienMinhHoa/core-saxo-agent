# Iteration 138 - fail-closed reference tại API route

## Phạm vi

Khóa một khe nhỏ trong policy file safety: route trước đây dùng `strip()` cho
`document_ref` và `asset_ref`, nên input có khoảng trắng đầu/cuối bị đổi thành
giá trị khác rồi mới được kiểm tra. Điều này không còn là một reference
canonical như policy domain yêu cầu.

## Thay đổi

- Thêm `_normalized_reference()` cho các route document và asset.
- Vẫn trim text tự do như query/question, nhưng reference có khoảng trắng đầu/cuối
  bị từ chối với HTTP 422 trước khi gọi workflow, repository hoặc resolver.
- Thêm regression tests cho source upload và asset route; cả hai chứng minh
  provider boundary không bị gọi.

## Bằng chứng kiểm thử

```text
uv run pytest tests/test_phase_7_api_routes.py -q
uv run python -m compileall -q src tests
git diff --check
```

Kết quả:

```text
tests/test_phase_7_api_routes.py: 32 passed, 1 warning
full suite: 612 passed, 3 skipped, 1 warning
compileall: passed
git diff --check: passed
```

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể chạy vì
checkout không có endpoint, credential và catalog production thật.
