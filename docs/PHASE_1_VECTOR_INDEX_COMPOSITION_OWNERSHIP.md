# Phase 1 - Composition root giữ ownership của VectorIndex

## Phạm vi lát cắt

Theo hướng Clean Code, `VectorIndex` là dependency hạ tầng được đưa vào
composition root qua `AppOverrides`. Trước lát cắt này, `IndexDocument` đã dùng
đúng object được inject nhưng `AppContainer` không lưu lại dependency đó. Điều
này làm mất khả năng kiểm tra lifecycle/diagnostics của application instance và
làm mờ ranh giới ownership khi chuẩn bị nối Chroma production.

## Thay đổi

- Thêm `vector_index` vào `AppContainer` với kiểu application port
  `VectorIndex | None`.
- Composition root giữ nguyên object `AppOverrides.vector_index` trong
  container; không tạo fallback local hoặc import SDK ở application use case.
- Bổ sung contract test xác nhận identity của dependency được giữ nguyên.

## Bằng chứng kiểm tra

```text
uv run pytest -q tests/test_phase_1_composition_root.py::test_indexing_composition_uses_durable_reuse_store_by_default
1 passed, 1 warning

python -m compileall -q src tests
pass

git diff --check
pass (chỉ còn cảnh báo chuẩn hóa LF/CRLF của Git trên Windows)
```

## Giới hạn còn lại

Lát cắt này chưa tự ý chọn đường dẫn persistent Chroma, tên collection hoặc
embedding function production. Các quyết định đó cần contract/settings riêng;
do đó live Chroma smoke test và composition adapter cụ thể vẫn là bước kế tiếp.
