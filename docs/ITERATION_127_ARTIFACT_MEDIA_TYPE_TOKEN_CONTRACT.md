# Iteration 127 - Contract token cho MIME của artifact

## Phạm vi

Iteration này tiếp tục hardening `ArtifactRef` theo phần Security và file safety
của `docs/SOLUTION_ARCHITECTURE_REFACTOR_PLAN.md`. Sau khi đã chặn whitespace và
control character, type/subtype của MIME cũng phải là token ASCII hợp lệ; nếu
không, metadata có thể chứa ký tự phân cách hoặc Unicode ngoài contract.

## Thay đổi

- `is_safe_media_type()` chỉ chấp nhận type/subtype gồm ký tự chữ/số và nhóm
  token punctuation chuẩn, vẫn hỗ trợ `+json`, dấu chấm và dấu gạch ngang.
- Bổ sung regression tests cho dấu ngoặc, dấu phẩy và Unicode không hợp lệ.
- Giữ nguyên MIME parameter hợp lệ như `application/json; charset=utf-8`.

## Kiểm chứng

```text
uv run pytest tests/test_phase_2_artifact_reference_contract.py -q
uv run pytest -q
python -m compileall -q src tests
git diff --check
```

Kết quả:

- targeted contract: **48 passed**;
- full suite: **554 passed, 3 skipped, 1 warning**;
- `compileall`: đạt;
- `git diff --check`: đạt.

Một test symbolic-link được skip vì Windows checkout hiện tại không có quyền tạo
symbolic link. Live model-service smoke và production golden parity vẫn phụ thuộc
endpoint, credential và catalog production chưa có trong checkout này.
