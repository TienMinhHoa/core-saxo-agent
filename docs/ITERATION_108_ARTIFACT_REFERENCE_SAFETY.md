# Iteration 108 - An toàn identity của artifact

## Phạm vi

Siết invariant của `ArtifactRef.artifact_id` theo yêu cầu file safety trong
`docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`: identity được phép là relative
reference có thể chứa các segment lồng nhau, nhưng không được biến thành path
tùy ý hoặc thoát khỏi artifact root.

## Thay đổi

- Thêm policy dùng chung `is_safe_artifact_reference`.
- `ArtifactRef` fail-closed ngay khi nhận artifact ID có `..`, `.`, segment rỗng,
  absolute path, backslash, NUL hoặc drive/scheme separator `:`.
- Giữ nguyên các identity hợp lệ như `document-123/manifest`, vì artifact
  repository vẫn cần namespace lồng nhau.
- Cập nhật contract tests cho traversal, absolute path, Windows path và identity
  không canonical; test storage cũ được chuyển sang kiểm tra lỗi tại domain
  boundary trước filesystem I/O.

## Bằng chứng kiểm thử

Lệnh targeted:

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py tests/test_phase_2_artifact_storage_contract.py tests/test_phase_3_process_document.py tests/test_phase_7_api_routes.py -q
59 passed, 1 warning
```

Full suite và kiểm tra chất lượng:

```text
uv run pytest -q
507 passed, 2 skipped, 1 warning

uv run python -m compileall -q src tests
git diff --check
```

`compileall` và `git diff --check` đều hoàn tất không có lỗi.

## Giới hạn còn lại

Live model-service smoke và production golden parity vẫn chưa thể xác minh vì
checkout chưa có endpoint, credential và catalog production thật.
